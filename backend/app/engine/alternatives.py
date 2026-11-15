import dataclasses
from dataclasses import dataclass, field
from datetime import timedelta

from app.engine import guesthouse, validator
from app.engine.availability import AvailabilityIndex
from app.engine.parking import check_parking as plan_parking
from app.engine.proposal import check_request
from app.engine.search import walking_minutes
from app.engine.types import BookingInfo, BookingRequest, Snapshot, VenueInfo
from app.rules import Rules

SUBSTITUTE_TYPES = {"classroom": ["seminar_hall"], "seminar_hall": ["classroom"], "amphitheatre": ["seminar_hall"], "lab": []}
TIME_STEP_MIN = 15


@dataclass
class Alternative:
    requests: list[BookingRequest]
    cost: int
    changes: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    approval_chain: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return "; ".join(self.changes) if self.changes else "same as requested"

    def as_dict(self, snapshot: Snapshot) -> dict:
        parts = []
        for request in self.requests:
            code = snapshot.venue(request.resource_id).code if request.resource_type == "venue" else str(request.resource_id)
            parts.append({"resource_type": request.resource_type, "resource_id": request.resource_id, "resource_code": code, "start": request.start.isoformat(), "end": request.end.isoformat(), "attendees": request.attendees})
        return {"parts": parts, "cost": self.cost, "what_changed": self.summary(), "citations": self.citations, "approval_chain": self.approval_chain}


def with_window(request: BookingRequest, **changes) -> BookingRequest:
    return dataclasses.replace(request, **changes)


def time_label(request: BookingRequest) -> str:
    return f"{request.start:%d %b %H:%M}-{request.end:%H:%M}"


def candidate_key(request: BookingRequest) -> tuple:
    return request.resource_type, request.resource_id, request.start, request.end


def venue_candidates(snapshot: Snapshot, rules: Rules, request: BookingRequest) -> list[tuple[BookingRequest, int, list[str], set[str]]]:
    weights = rules.alternatives
    original = snapshot.venue(request.resource_id)
    duration = request.end - request.start
    venue_options: list[tuple[VenueInfo, int, list[str], set[str]]] = [(original, 0, [], set())]
    for venue in snapshot.venues:
        if venue.id == original.id or not venue.bookable:
            continue
        same_type = venue.type == original.type
        if not same_type and venue.type not in SUBSTITUTE_TYPES[original.type]:
            continue
        missing = [f for f in request.features if f not in venue.features]
        if len(missing) > 1:
            continue
        cost = weights.other_venue if same_type else weights.substitute_type
        notes = [f"moved to {venue.code}" if same_type else f"substituted {original.type} with {venue.type} {venue.code}"]
        if venue.building_id != original.building_id:
            cost += weights.other_building
            notes.append(f"different building ({walking_minutes(snapshot, original.building_id, venue.building_id)} min walk)")
        if missing:
            cost += weights.drop_feature * len(missing)
            notes.append(f"drops feature {', '.join(missing)}")
        venue_options.append((venue, cost, notes, {"BP-9.3"}))
    time_options: list[tuple[timedelta, int, list[str]]] = [(timedelta(0), 0, [])]
    steps = weights.max_time_shift_min // TIME_STEP_MIN
    for step in range(1, steps + 1):
        for sign in (1, -1):
            shift = timedelta(minutes=sign * step * TIME_STEP_MIN)
            time_options.append((shift, step * weights.shift_time_per_15min, [f"shifted {sign * step * TIME_STEP_MIN:+d} min"]))
    for days in range(1, weights.max_day_shift + 1):
        for sign in (1, -1):
            time_options.append((timedelta(days=sign * days), days * weights.shift_day_per_day, [f"moved {sign * days:+d} day"]))
    found: list[tuple[BookingRequest, int, list[str], set[str]]] = []
    for venue, venue_cost, venue_notes, cites in venue_options:
        for shift, shift_cost, shift_notes in time_options:
            cost = venue_cost + shift_cost
            if cost == 0:
                continue
            found.append((with_window(request, resource_id=venue.id, start=request.start + shift, end=request.end + shift), cost, venue_notes + shift_notes, cites | ({"BP-9.3"} if shift_notes else set())))
    quarter = timedelta(minutes=TIME_STEP_MIN)
    for step in range(1, int(duration / quarter) - 1):
        shorter = duration - step * quarter
        if shorter < timedelta(minutes=30):
            break
        found.append((with_window(request, end=request.start + shorter), step * weights.shorten_per_15min, [f"shortened by {step * TIME_STEP_MIN} min"], {"BP-9.3"}))
    return found


def verify_candidate(index: AvailabilityIndex, rules: Rules, request: BookingRequest) -> tuple[bool, list[str]]:
    result = check_request(index, rules, request)
    if not result.ok:
        return False, []
    snapshot = index.snapshot
    pending = BookingInfo(
        id=-1, bundle_id=None, resource_type="venue", resource_id=request.resource_id, qty=1, requester_id=0, event_title="candidate", attendees=request.attendees,
        start_dt=request.start, end_dt=request.end, priority_class=4, status="CONFIRMED", hold_expires_at=None, meta={},
    )
    probe = dataclasses.replace(snapshot, bookings=snapshot.bookings + [pending])
    clean = not validator.validate(probe, rules, {("venue", request.resource_id)})
    return clean, [v.rule_id for v in result.violations if v.severity == "soft"]


def split_candidates(index: AvailabilityIndex, rules: Rules, request: BookingRequest) -> list[Alternative]:
    snapshot = index.snapshot
    original = snapshot.venue(request.resource_id)
    free = [v for v in snapshot.venues if v.type == original.type and v.id != original.id and index.is_free(v.id, request.start, request.end)]
    free.sort(key=lambda v: -v.capacity)
    if len(free) < 2 or request.attendees <= free[0].capacity:
        return []
    first, second = free[0], free[1]
    if first.capacity + second.capacity < request.attendees:
        return []
    share = request.attendees - first.capacity
    parts = [with_window(request, resource_id=first.id, attendees=first.capacity), with_window(request, resource_id=second.id, attendees=share)]
    return [Alternative(parts, rules.alternatives.split_venues, [f"split across {first.code} and {second.code}"], ["BP-9.3"])]


def recommend_alternatives(index: AvailabilityIndex, rules: Rules, request: BookingRequest, limit: int = 5) -> list[Alternative]:
    if request.resource_type == "guest_room":
        return guest_alternatives(index, rules, request, limit)
    if request.resource_type == "parking":
        return parking_alternatives(index, rules, request, limit)
    snapshot = index.snapshot
    candidates = venue_candidates(snapshot, rules, request)
    candidates.sort(key=lambda item: (item[1], item[0].resource_id))
    seen: set[tuple] = set()
    chosen: list[Alternative] = []
    for candidate, cost, notes, cites in candidates:
        key = candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        if not candidate_in_range(index, candidate) or not index.is_free(candidate.resource_id, candidate.start, candidate.end):
            continue
        ok, soft_rules = verify_candidate(index, rules, candidate)
        if ok:
            chain = check_request(index, rules, candidate).approval_chain
            chosen.append(Alternative([candidate], cost, notes, sorted(cites | set(soft_rules)), chain))
        if len(chosen) >= limit:
            break
    if len(chosen) < limit:
        chosen.extend(split_candidates(index, rules, request))
    chosen.sort(key=lambda alt: alt.cost)
    return chosen[:limit]


def candidate_in_range(index: AvailabilityIndex, request: BookingRequest) -> bool:
    return index.covers(request.start, request.end)


def guest_alternatives(index: AvailabilityIndex, rules: Rules, request: BookingRequest, limit: int) -> list[Alternative]:
    snapshot = index.snapshot
    weights = rules.alternatives
    guests = request.meta.get("guests", 1)
    options: list[Alternative] = []
    for room in guesthouse.available_rooms(snapshot, rules, request.start, request.end, guests):
        if room.id != request.resource_id:
            options.append(Alternative([with_window(request, resource_id=room.id)], weights.other_venue, [f"other room {room.code} ({room.type})"], ["BP-9.3"]))
    for days in range(1, weights.max_day_shift + 1):
        for sign in (1, -1):
            start = request.start + timedelta(days=sign * days)
            end = request.end + timedelta(days=sign * days)
            for room in guesthouse.rank_rooms(guesthouse.available_rooms(snapshot, rules, start, end, guests), guests, "other")[:1]:
                options.append(Alternative([with_window(request, resource_id=room.id, start=start, end=end)], days * weights.shift_day_per_day, [f"stay moved {sign * days:+d} day in {room.code}"], ["BP-9.3"]))
    options.sort(key=lambda alt: alt.cost)
    return options[:limit]


def parking_alternatives(index: AvailabilityIndex, rules: Rules, request: BookingRequest, limit: int) -> list[Alternative]:
    snapshot = index.snapshot
    weights = rules.alternatives
    vehicles = request.meta.get("vehicles") or {"car": request.qty}
    options: list[Alternative] = []
    plan = plan_parking(snapshot, rules, request.start, request.end, vehicles)
    if plan.ok and len(plan.allocations) > 1:
        parts = [with_window(request, resource_id=a.lot_id, qty=sum(a.vehicles.values()), meta={**request.meta, "vehicles": a.vehicles}) for a in plan.allocations]
        options.append(Alternative(parts, weights.split_venues, ["split across lots with a shuttle note"], ["BP-6.8"]))
    for step in range(1, weights.max_time_shift_min // TIME_STEP_MIN + 1):
        for sign in (1, -1):
            shift = timedelta(minutes=sign * step * TIME_STEP_MIN)
            moved = plan_parking(snapshot, rules, request.start + shift, request.end + shift, vehicles)
            if moved.ok and len(moved.allocations) == 1:
                lot = moved.allocations[0]
                options.append(Alternative([with_window(request, resource_id=lot.lot_id, start=request.start + shift, end=request.end + shift)], step * weights.shift_time_per_15min, [f"window shifted {sign * step * TIME_STEP_MIN:+d} min in {lot.lot_name}"], ["BP-9.3"]))
                break
    options.sort(key=lambda alt: alt.cost)
    return options[:limit]
