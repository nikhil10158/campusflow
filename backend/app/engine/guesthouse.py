from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ortools.sat.python import cp_model

from app.engine.availability import booking_is_active
from app.engine.types import BookingInfo, GuestRoomInfo, Snapshot
from app.rules import Rules

SUITE_CATEGORIES = ("vip", "official")
ROOM_RANK = {"standard": 0, "deluxe": 1, "suite": 2}


@dataclass
class GuestSpec:
    name: str
    category: str = "other"
    needs_accessible: bool = False


@dataclass
class Allocation:
    assignments: dict[int, int] = field(default_factory=dict)
    rooms_used: int = 0
    tariff_total: int = 0
    suite_misuse: int = 0
    violations: list[str] = field(default_factory=list)
    status: str = "OPTIMAL"


def blocked_intervals(snapshot: Snapshot, room_id: int, exclude_booking_id: int | None = None) -> list[tuple[datetime, datetime]]:
    found = [
        (b.start_dt, b.end_dt)
        for b in snapshot.bookings
        if b.resource_type == "guest_room" and b.resource_id == room_id and b.id != exclude_booking_id and booking_is_active(b, snapshot.now)
    ]
    found += [(m.start_dt, m.end_dt) for m in snapshot.maintenance if m.resource_type == "guest_room" and m.resource_id == room_id]
    return found


def room_available(snapshot: Snapshot, rules: Rules, room_id: int, start: datetime, end: datetime, exclude_booking_id: int | None = None) -> bool:
    turnover = timedelta(minutes=rules.resources["guest_room"].turnover_buffer_min)
    room = next((r for r in snapshot.guest_rooms if r.id == room_id), None)
    if room is None or room.status != "active":
        return False
    return not any(start < busy_end + turnover and busy_start < end + turnover for busy_start, busy_end in blocked_intervals(snapshot, room_id, exclude_booking_id))


def available_rooms(snapshot: Snapshot, rules: Rules, start: datetime, end: datetime, guests: int = 1, accessible: bool = False) -> list[GuestRoomInfo]:
    return [
        room for room in snapshot.guest_rooms
        if room.capacity >= guests and (room.accessible or not accessible) and room_available(snapshot, rules, room.id, start, end)
    ]


def rank_rooms(rooms: list[GuestRoomInfo], guests: int, category: str) -> list[GuestRoomInfo]:
    def key(room: GuestRoomInfo) -> tuple[int, int, int]:
        suite_penalty = 1 if room.type == "suite" and category not in SUITE_CATEGORIES else 0
        suite_bonus = -1 if room.type == "suite" and category in SUITE_CATEGORIES else 0
        return suite_penalty + suite_bonus, room.capacity - guests, room.tariff_per_night
    return sorted(rooms, key=key)


def best_fit(snapshot: Snapshot, rules: Rules, start: datetime, end: datetime, guests: int, category: str, accessible: bool = False) -> list[GuestRoomInfo]:
    return rank_rooms(available_rooms(snapshot, rules, start, end, guests, accessible), guests, category)


def tariff_estimate(room: GuestRoomInfo, start: datetime, end: datetime) -> int:
    return room.tariff_per_night * max(1, (end.date() - start.date()).days)


def is_suite_misuse(room: GuestRoomInfo, guest: GuestSpec) -> bool:
    return room.type == "suite" and guest.category not in SUITE_CATEGORIES


def score_allocation(rooms: list[GuestRoomInfo], guests: list[GuestSpec], assignments: dict[int, int]) -> Allocation:
    by_id = {r.id: r for r in rooms}
    used = set(assignments.values())
    return Allocation(
        assignments=assignments,
        rooms_used=len(used),
        tariff_total=sum(by_id[r].tariff_per_night for r in used),
        suite_misuse=sum(1 for g, r in assignments.items() if is_suite_misuse(by_id[r], guests[g])),
    )


def greedy_allocate(rooms: list[GuestRoomInfo], guests: list[GuestSpec], must_not_share: list[tuple[int, int]]) -> Allocation:
    order = sorted(range(len(guests)), key=lambda g: (guests[g].category not in SUITE_CATEGORIES, g))
    assignments: dict[int, int] = {}
    occupants: dict[int, list[int]] = {}
    for guest_index in order:
        guest = guests[guest_index]
        placed = False
        for room in sorted(rooms, key=lambda r: (r.id not in occupants, -ROOM_RANK[r.type] if guest.category in SUITE_CATEGORIES else r.tariff_per_night)):
            current = occupants.get(room.id, [])
            if guest.needs_accessible and not room.accessible:
                continue
            if len(current) >= room.capacity:
                continue
            if any((guest_index, other) in must_not_share or (other, guest_index) in must_not_share for other in current):
                continue
            occupants.setdefault(room.id, []).append(guest_index)
            assignments[guest_index] = room.id
            placed = True
            break
        if not placed:
            return Allocation(assignments, status="INFEASIBLE", violations=[f"No room for {guest.name}"])
    return score_allocation(rooms, guests, assignments)


def group_allocate(rooms: list[GuestRoomInfo], guests: list[GuestSpec], must_share: list[tuple[int, int]], must_not_share: list[tuple[int, int]], time_limit: float = 5.0, workers: int = 4) -> Allocation:
    model = cp_model.CpModel()
    assign = {(g, r.id): model.NewBoolVar(f"g{g}_r{r.id}") for g in range(len(guests)) for r in rooms}
    used = {r.id: model.NewBoolVar(f"used_{r.id}") for r in rooms}
    for g, guest in enumerate(guests):
        model.AddExactlyOne(assign[g, r.id] for r in rooms)
        for r in rooms:
            if guest.needs_accessible and not r.accessible:
                model.Add(assign[g, r.id] == 0)
    for r in rooms:
        model.Add(sum(assign[g, r.id] for g in range(len(guests))) <= r.capacity)
        for g in range(len(guests)):
            model.AddImplication(assign[g, r.id], used[r.id])
    for a, b in must_share:
        for r in rooms:
            model.Add(assign[a, r.id] == assign[b, r.id])
    for a, b in must_not_share:
        for r in rooms:
            model.Add(assign[a, r.id] + assign[b, r.id] <= 1)
    misuse = [assign[g, r.id] for g, guest in enumerate(guests) for r in rooms if is_suite_misuse(r, guest)]
    model.Minimize(100000 * sum(used.values()) + 10 * sum(r.tariff_per_night * used[r.id] for r in rooms) + 5000 * sum(misuse))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Allocation(status="INFEASIBLE", violations=["No allocation satisfies the constraints"])
    assignments = {g: next(r.id for r in rooms if solver.Value(assign[g, r.id])) for g in range(len(guests))}
    result = score_allocation(rooms, guests, assignments)
    result.status = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
    return result


def waitlist_order(bookings: list[BookingInfo]) -> list[BookingInfo]:
    return sorted([b for b in bookings if b.status == "WAITLISTED"], key=lambda b: (b.priority_class, b.id))


def promotion_candidates(snapshot: Snapshot, rules: Rules) -> list[dict]:
    proposals: list[dict] = []
    taken: dict[int, list[tuple[datetime, datetime]]] = {}
    for waiting in waitlist_order(snapshot.bookings):
        wanted_type = waiting.meta.get("requested_type")
        guests = waiting.meta.get("guests", 1)
        for room in snapshot.guest_rooms:
            if (wanted_type and room.type != wanted_type) or room.capacity < guests:
                continue
            clash = any(waiting.start_dt < e and s < waiting.end_dt for s, e in taken.get(room.id, []))
            if not clash and room_available(snapshot, rules, room.id, waiting.start_dt, waiting.end_dt, exclude_booking_id=waiting.id):
                taken.setdefault(room.id, []).append((waiting.start_dt, waiting.end_dt))
                proposals.append({"booking_id": waiting.id, "room_id": room.id, "room_code": room.code, "priority_class": waiting.priority_class, "title": waiting.event_title})
                break
    return proposals
