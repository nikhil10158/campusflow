import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.engine import batch
from app.engine.alternatives import SUBSTITUTE_TYPES
from app.engine.availability import AvailabilityIndex, booking_is_active
from app.engine.parking import check_parking, vehicles_of
from app.engine.search import walking_minutes
from app.engine.timeutil import at_minute, date_range
from app.engine.types import BookingInfo, EntryInfo, Snapshot, VenueInfo
from app.rules import Rules

SHIFTS_MIN = [0, 30, -30, 60, -60]
MAX_OPTIONS_PER_ITEM = 12


@dataclass
class Closure:
    kind: str
    start: datetime
    end: datetime
    venue_ids: list[int] = field(default_factory=list)
    faculty_id: int | None = None
    lot_id: int | None = None
    description: str = ""


@dataclass
class AffectedItem:
    key: str
    kind: str
    source_id: int
    label: str
    venue_id: int | None
    start: datetime
    end: datetime
    severity: str
    size: int
    allow_shift: bool


def class_occurrences(snapshot: Snapshot, venue_ids: set[int], first: date, last: date) -> list[tuple[EntryInfo, date]]:
    cleared = {(e.entry_id, e.date) for e in snapshot.exceptions if e.status == "APPROVED" and e.type in ("cancelled", "released", "moved")}
    found: list[tuple[EntryInfo, date]] = []
    for entry in snapshot.entries:
        if entry.venue_id not in venue_ids:
            continue
        for day in date_range(first, last):
            if day.weekday() == entry.weekday and entry.effective_from <= day <= entry.effective_to and day not in snapshot.holidays and (entry.id, day) not in cleared:
                found.append((entry, day))
    return found


def affected_items(snapshot: Snapshot, closure: Closure) -> list[AffectedItem]:
    items: list[AffectedItem] = []
    closed = set(closure.venue_ids)
    for entry, day in class_occurrences(snapshot, closed, closure.start.date(), closure.end.date()):
        start, end = at_minute(day, entry.start_min), at_minute(day, entry.end_min)
        if start < closure.end and closure.start < end:
            section = snapshot.sections.get(entry.section_id)
            size = section.size if section else 0
            if entry.kind == "lab":
                size = min(size, snapshot.venue(entry.venue_id).capacity)
            label = f"{entry.course_code} {entry.kind} ({section.dept} Sem {section.semester}-{section.name})" if section else entry.course_code
            items.append(AffectedItem(f"class:{entry.id}:{day}", "class", entry.id, label, entry.venue_id, start, end, "medium", size, False))
    for booking in snapshot.bookings:
        if booking.resource_type == "venue" and booking.resource_id in closed and booking_is_active(booking, snapshot.now) and booking.start_dt < closure.end and closure.start < booking.end_dt:
            severity = "high" if booking.status == "CONFIRMED" and booking.attendees > 100 else "medium" if booking.status == "CONFIRMED" else "low"
            items.append(AffectedItem(f"booking:{booking.id}", "booking", booking.id, booking.event_title, booking.resource_id, booking.start_dt, booking.end_dt, severity, booking.attendees, True))
    return items


def pool_for(snapshot: Snapshot, original: VenueInfo, closed: set[int], size: int) -> list[VenueInfo]:
    allowed_types = [original.type] + SUBSTITUTE_TYPES[original.type]
    return [v for v in snapshot.venues if v.id not in closed and v.bookable and v.type in allowed_types and v.capacity >= size and (original.type != "lab" or v.lab_type == original.lab_type)]


def options_for(index: AvailabilityIndex, rules: Rules, item: AffectedItem, closed: set[int]) -> list[batch.Option]:
    snapshot = index.snapshot
    weights = rules.alternatives
    original = snapshot.venue(item.venue_id)
    options: list[tuple[int, batch.Option]] = []
    for venue in pool_for(snapshot, original, closed, item.size):
        base = weights.other_venue if venue.type == original.type else weights.substitute_type
        if venue.building_id != original.building_id:
            base += weights.other_building
        for shift in SHIFTS_MIN if item.allow_shift else [0]:
            start = item.start + timedelta(minutes=shift)
            end = item.end + timedelta(minutes=shift)
            if index.covers(start, end) and index.is_free(venue.id, start, end):
                cost = base + abs(shift) // 15 * weights.shift_time_per_15min
                options.append((cost, batch.Option(venue.id, start, end, max(10, 100 - cost * 3), venue.capacity)))
    options.sort(key=lambda pair: (pair[0], pair[1].venue_id))
    return [option for _, option in options[:MAX_OPTIONS_PER_ITEM]]


def describe_option(snapshot: Snapshot, item: AffectedItem, option: batch.Option) -> dict:
    venue = snapshot.venue(option.venue_id)
    original = snapshot.venue(item.venue_id)
    cost = (100 - option.satisfaction) // 3
    return {
        "venue_id": venue.id, "venue_code": venue.code, "start": option.start.isoformat(), "end": option.end.isoformat(), "cost": cost,
        "walk_min": walking_minutes(snapshot, original.building_id, venue.building_id),
        "what_changed": f"moved from {original.code} to {venue.code}" + (f", {int((option.start - item.start).total_seconds() // 60):+d} min" if option.start != item.start else ""),
    }


def assess_venue_closure(index: AvailabilityIndex, rules: Rules, closure: Closure, time_limit: float, workers: int) -> dict:
    snapshot = index.snapshot
    closed = set(closure.venue_ids)
    items = affected_items(snapshot, closure)
    events: list[batch.EventRequest] = []
    for number, item in enumerate(items, start=1):
        weight = {"high": 5, "medium": 3, "low": 2}[item.severity]
        events.append(batch.EventRequest(number, item.key, weight, item.size, options_for(index, rules, item, closed)))
    solved = batch.optimise(snapshot, events, time_limit, workers) if events else None
    results: list[dict] = []
    resolved = 0
    for number, item in enumerate(items, start=1):
        event = events[number - 1]
        chosen = solved.chosen.get(number) if solved else None
        if chosen:
            resolved += 1
        results.append({
            "key": item.key, "kind": item.kind, "source_id": item.source_id, "label": item.label, "venue_code": snapshot.venue(item.venue_id).code,
            "date": item.start.date().isoformat(), "start": item.start.isoformat(), "end": item.end.isoformat(), "severity": item.severity,
            "proposal": describe_option(snapshot, item, chosen) if chosen else None,
            "alternatives": [describe_option(snapshot, item, o) for o in event.options[:3]],
        })
    return {
        "kind": "venue_closure", "description": closure.description, "affected": len(items), "resolved": resolved, "unresolved": len(items) - resolved,
        "solver": solved.as_dict() | {"assignments": []} if solved else None, "items": results,
    }


def assess_faculty_absence(snapshot: Snapshot, closure: Closure) -> dict:
    items: list[dict] = []
    cleared = {(e.entry_id, e.date) for e in snapshot.exceptions if e.status == "APPROVED" and e.type in ("cancelled", "released", "moved")}
    for entry in snapshot.entries:
        if entry.faculty_id != closure.faculty_id:
            continue
        for day in date_range(closure.start.date(), closure.end.date()):
            if day.weekday() == entry.weekday and entry.effective_from <= day <= entry.effective_to and day not in snapshot.holidays and (entry.id, day) not in cleared:
                items.append({
                    "key": f"class:{entry.id}:{day}", "kind": "class", "source_id": entry.id, "label": f"{entry.course_code} {entry.kind}", "venue_code": snapshot.venue(entry.venue_id).code,
                    "date": day.isoformat(), "start": at_minute(day, entry.start_min).isoformat(), "end": at_minute(day, entry.end_min).isoformat(), "severity": "medium",
                    "proposal": {"action": "cancel", "entry_id": entry.id, "date": day.isoformat(), "what_changed": "cancel the class and free the room"}, "alternatives": [],
                })
    return {"kind": "faculty_absence", "description": closure.description, "affected": len(items), "resolved": len(items), "unresolved": 0, "items": items}


def assess_lot_closure(index: AvailabilityIndex, rules: Rules, closure: Closure) -> dict:
    snapshot = index.snapshot
    closed_lot = dataclasses.replace(next(l for l in snapshot.lots if l.id == closure.lot_id), cap_car=0, cap_bike=0, cap_bus=0, ev_bays=0, vip_bays=0)
    reduced = dataclasses.replace(snapshot, lots=[closed_lot if l.id == closure.lot_id else l for l in snapshot.lots])
    items: list[dict] = []
    for booking in snapshot.bookings:
        if booking.resource_type != "parking" or booking.resource_id != closure.lot_id or not booking_is_active(booking, snapshot.now):
            continue
        if not (booking.start_dt < closure.end and closure.start < booking.end_dt):
            continue
        plan = check_parking(reduced, rules, booking.start_dt, booking.end_dt, vehicles_of(booking.meta, booking.qty), exclude_booking_id=booking.id)
        items.append({
            "key": f"booking:{booking.id}", "kind": "booking", "source_id": booking.id, "label": booking.event_title, "venue_code": closed_lot.name,
            "date": booking.start_dt.date().isoformat(), "start": booking.start_dt.isoformat(), "end": booking.end_dt.isoformat(),
            "severity": "medium", "alternatives": [],
            "proposal": {"action": "move_parking", "allocations": [{"lot_id": a.lot_id, "lot_name": a.lot_name, "vehicles": a.vehicles, "shuttle": a.shuttle} for a in plan.allocations], "unmet": plan.unmet, "what_changed": "move to " + ", ".join(a.lot_name for a in plan.allocations)} if plan.ok else None,
        })
    resolved = sum(1 for i in items if i["proposal"])
    return {"kind": "lot_closure", "description": closure.description, "affected": len(items), "resolved": resolved, "unresolved": len(items) - resolved, "items": items}


def assess(index: AvailabilityIndex, rules: Rules, closure: Closure, time_limit: float = 5.0, workers: int = 4) -> dict:
    if closure.kind == "faculty":
        return assess_faculty_absence(index.snapshot, closure)
    if closure.kind == "lot":
        return assess_lot_closure(index, rules, closure)
    return assess_venue_closure(index, rules, closure, time_limit, workers)
