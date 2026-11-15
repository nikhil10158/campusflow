from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from app.engine.availability import booking_is_active
from app.engine.timeutil import SLOTS_PER_DAY, day_pieces
from app.engine.types import LotInfo, Snapshot
from app.rules import Rules

VEHICLE_TYPES = ("car", "bike", "bus", "ev", "vip")
SHUTTLE_DISTANCE_M = 400


@dataclass
class LotAllocation:
    lot_id: int
    lot_name: str
    vehicles: dict[str, int]
    distance_m: int | None
    shuttle: bool


@dataclass
class ParkingPlan:
    allocations: list[LotAllocation] = field(default_factory=list)
    unmet: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.unmet


def raw_capacity(lot: LotInfo, vehicle: str) -> int:
    return {"car": lot.cap_car, "bike": lot.cap_bike, "bus": lot.cap_bus, "ev": lot.ev_bays, "vip": lot.vip_bays}[vehicle]


def reservable_capacity(lot: LotInfo, vehicle: str, rules: Rules) -> int:
    return raw_capacity(lot, vehicle) * (100 - rules.walkin_reserve_pct) // 100


def lot_allows(lot: LotInfo, vehicle: str) -> bool:
    if raw_capacity(lot, vehicle) <= 0:
        return False
    if vehicle == "vip":
        return True
    return lot.visitor_allowed


def vehicles_of(booking_meta: dict, qty: int) -> dict[str, int]:
    vehicles = booking_meta.get("vehicles")
    return dict(vehicles) if vehicles else {"car": qty}


def occupancy(snapshot: Snapshot, lot_id: int, vehicle: str, start: datetime, end: datetime) -> np.ndarray:
    pieces = list(day_pieces(start, end))
    counts = {day: np.zeros(SLOTS_PER_DAY, dtype=int) for day, _, _ in pieces}
    for booking in snapshot.bookings:
        if booking.resource_type != "parking" or booking.resource_id != lot_id or not booking_is_active(booking, snapshot.now):
            continue
        amount = vehicles_of(booking.meta, booking.qty).get(vehicle, 0)
        if amount:
            for day, low, high in day_pieces(booking.start_dt, booking.end_dt):
                if day in counts:
                    counts[day][low:high] += amount
    return np.concatenate([counts[day][low:high] for day, low, high in pieces]) if pieces else np.zeros(0, dtype=int)


def free_capacity(snapshot: Snapshot, rules: Rules, lot: LotInfo, vehicle: str, start: datetime, end: datetime, exclude_booking_id: int | None = None) -> int:
    if exclude_booking_id is not None:
        snapshot = without_booking(snapshot, exclude_booking_id)
    used = occupancy(snapshot, lot.id, vehicle, start, end)
    peak = int(used.max()) if used.size else 0
    return max(0, reservable_capacity(lot, vehicle, rules) - peak)


def without_booking(snapshot: Snapshot, booking_id: int) -> Snapshot:
    clone = Snapshot(**{name: getattr(snapshot, name) for name in snapshot.__dataclass_fields__})
    clone.bookings = [b for b in snapshot.bookings if b.id != booking_id]
    return clone


def lot_timeline(snapshot: Snapshot, rules: Rules, lot: LotInfo, vehicle: str, start: datetime, end: datetime) -> dict:
    used = occupancy(snapshot, lot.id, vehicle, start, end)
    return {"capacity": reservable_capacity(lot, vehicle, rules), "raw_capacity": raw_capacity(lot, vehicle), "used": used.tolist(), "first_slot_start": start.isoformat()}


def check_parking(snapshot: Snapshot, rules: Rules, start: datetime, end: datetime, vehicles: dict[str, int], near_venue_id: int | None = None, exclude_booking_id: int | None = None) -> ParkingPlan:
    near_building = snapshot.venue(near_venue_id).building_id if near_venue_id else None
    plan = ParkingPlan()
    placed: dict[int, dict[str, int]] = {}
    for vehicle, wanted in vehicles.items():
        remaining = wanted
        candidates = [lot for lot in snapshot.lots if lot_allows(lot, vehicle)]
        candidates.sort(key=lambda lot: (lot.near.get(str(near_building), 10 ** 6) if near_building else 0, -raw_capacity(lot, vehicle), lot.id))
        for lot in candidates:
            if remaining <= 0:
                break
            room = free_capacity(snapshot, rules, lot, vehicle, start, end, exclude_booking_id)
            take = min(room, remaining)
            if take > 0:
                placed.setdefault(lot.id, {})[vehicle] = placed.get(lot.id, {}).get(vehicle, 0) + take
                remaining -= take
        if remaining > 0:
            plan.unmet[vehicle] = remaining
    lots = {lot.id: lot for lot in snapshot.lots}
    for lot_id, counts in placed.items():
        lot = lots[lot_id]
        distance = lot.near.get(str(near_building)) if near_building else None
        shuttle = len(placed) > 1 or (distance is not None and distance > SHUTTLE_DISTANCE_M)
        plan.allocations.append(LotAllocation(lot_id, lot.name, counts, distance, shuttle))
    plan.allocations.sort(key=lambda a: a.distance_m if a.distance_m is not None else 0)
    return plan


def no_show_candidates(snapshot: Snapshot, rules: Rules, scanned_booking_ids: set[int]) -> list[int]:
    grace = timedelta(minutes=rules.no_show_grace_min)
    return [
        b.id for b in snapshot.bookings
        if b.resource_type == "parking" and b.status == "CONFIRMED" and b.start_dt + grace <= snapshot.now < b.end_dt and b.id not in scanned_booking_ids
    ]
