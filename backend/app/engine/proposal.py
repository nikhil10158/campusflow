from dataclasses import dataclass, field

from app.engine import guesthouse, parking, policy
from app.engine.approvals import approval_chain
from app.engine.availability import AvailabilityIndex
from app.engine.types import BookingRequest, Segment, Violation
from app.rules import Rules

BUFFER_RULE = {"seminar_hall": "BP-2.2", "amphitheatre": "BP-4.3", "classroom": "BP-2.3", "lab": "BP-3.4"}


@dataclass
class CheckResult:
    request: BookingRequest
    violations: list[Violation] = field(default_factory=list)
    state: str = "FREE"
    conflicts: list[str] = field(default_factory=list)
    blockers: list[Segment] = field(default_factory=list)
    approval_chain: list[str] = field(default_factory=list)

    @property
    def hard(self) -> list[Violation]:
        return policy.hard_only(self.violations)

    @property
    def ok(self) -> bool:
        return not self.hard and not self.conflicts

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "state": self.state,
            "violations": [v.as_dict() for v in self.violations],
            "conflicts": self.conflicts,
            "blockers": [b.as_dict() for b in self.blockers],
            "approval_chain": self.approval_chain,
        }


def check_venue(index: AvailabilityIndex, rules: Rules, request: BookingRequest, result: CheckResult) -> None:
    venue = index.snapshot.venue(request.resource_id)
    own = request.meta.get("exclude_booking_id")

    def foreign(blockers: list) -> list:
        return [b for b in blockers if not (own is not None and b.layer in ("held", "confirmed") and b.source_id == own)]

    availability = index.check(venue.id, request.start, request.end)
    blockers = foreign(availability.blockers)
    if blockers:
        result.state = "BUSY"
    else:
        result.state = availability.state if not availability.blockers else "FREE"
    result.blockers = blockers
    if not blockers:
        return
    if not foreign(index.check(venue.id, request.start, request.end, with_buffers=False).blockers):
        result.violations.append(policy.hard("P-BUFFER", BUFFER_RULE[venue.type], f"{venue.code} needs {venue.setup_buffer_min} min setup and {venue.teardown_buffer_min} min teardown around the booking"))
    result.conflicts = [f"{venue.code} busy {b.time_text()}: {b.label} ({b.layer})" for b in blockers]


def check_guest_room(index: AvailabilityIndex, rules: Rules, request: BookingRequest, result: CheckResult) -> None:
    snapshot = index.snapshot
    if not guesthouse.room_available(snapshot, rules, request.resource_id, request.start, request.end, request.meta.get("exclude_booking_id")):
        room = next((r.code for r in snapshot.guest_rooms if r.id == request.resource_id), str(request.resource_id))
        result.state = "BUSY"
        result.conflicts = [f"Guest room {room} is not free for those nights (turnover buffer included)"]


def check_parking(index: AvailabilityIndex, rules: Rules, request: BookingRequest, result: CheckResult) -> None:
    vehicles = request.meta.get("vehicles") or {"car": request.qty}
    lot = next(l for l in index.snapshot.lots if l.id == request.resource_id)
    exclude = request.meta.get("exclude_booking_id")
    for vehicle, wanted in vehicles.items():
        if not parking.lot_allows(lot, vehicle):
            result.conflicts.append(f"{lot.name} cannot take {vehicle} vehicles")
        elif parking.free_capacity(index.snapshot, rules, lot, vehicle, request.start, request.end, exclude) < wanted:
            result.conflicts.append(f"{lot.name} has fewer than {wanted} free {vehicle} spaces in that window")
    if result.conflicts:
        result.state = "BUSY"


def check_request(index: AvailabilityIndex, rules: Rules, request: BookingRequest, skip_lead: bool = False) -> CheckResult:
    snapshot = index.snapshot
    result = CheckResult(request)
    result.violations = policy.check(request, snapshot, rules, snapshot.now, skip_lead)
    if request.resource_type == "venue":
        check_venue(index, rules, request, result)
    elif request.resource_type == "guest_room":
        check_guest_room(index, rules, request, result)
    elif request.resource_type == "parking":
        check_parking(index, rules, request, result)
    result.approval_chain = approval_chain(request, snapshot, rules)
    return result
