from datetime import datetime, timedelta

from app.engine.timeutil import minute_of_day, nights_between, parse_hhmm
from app.engine.types import BookingRequest, Snapshot, VenueInfo, Violation
from app.rules import Rules

DURATION_RULE = {"classroom": "BP-2.1", "seminar_hall": "BP-2.2", "lab": "BP-3.4", "amphitheatre": "BP-4.5"}
FILL_RULE = {"classroom": "BP-2.4", "seminar_hall": "BP-2.4", "lab": "BP-3.4", "amphitheatre": "BP-4.4"}
DEPT_ROLES = ("faculty", "admin", "approver")


def hard(code: str, rule_id: str, message: str, fixable_by: str = "requester") -> Violation:
    return Violation(code, rule_id, "hard", message, fixable_by)


def soft(code: str, rule_id: str, message: str, fixable_by: str = "requester") -> Violation:
    return Violation(code, rule_id, "soft", message, fixable_by)


def venue_warnings(venue: VenueInfo, attendees: int, rules: Rules) -> list[Violation]:
    rule = rules.for_venue_type(venue.type)
    if attendees and venue.capacity and attendees / venue.capacity < rule.min_fill_ratio:
        return [soft(
            "P-CAPACITY",
            FILL_RULE[venue.type],
            f"{venue.code} would be {attendees * 100 // venue.capacity}% full; a smaller room is recommended below {int(rule.min_fill_ratio * 100)}%",
        )]
    return []


def timing_violations(request: BookingRequest, lead_hours: int, advance_days: int, now: datetime, skip_lead: bool) -> list[Violation]:
    found: list[Violation] = []
    if not skip_lead and request.start < now + timedelta(hours=lead_hours):
        found.append(hard("P-LEAD", "BP-1.4", f"Needs at least {lead_hours} hours of lead time before the start"))
    if request.start > now + timedelta(days=advance_days):
        found.append(hard("P-ADVANCE", "BP-1.5", f"Cannot be booked more than {advance_days} days ahead"))
    return found


def venue_violations(request: BookingRequest, venue: VenueInfo, rules: Rules, now: datetime, skip_lead: bool) -> list[Violation]:
    rule = rules.for_venue_type(venue.type)
    found = timing_violations(request, rule.lead_time_hours, rule.max_advance_days, now, skip_lead)
    minutes = int((request.end - request.start).total_seconds() // 60)
    if minutes <= 0:
        found.append(hard("P-DURATION", DURATION_RULE[venue.type], "End time must be after the start time"))
    elif minutes > rule.max_duration_min:
        found.append(hard("P-DURATION", DURATION_RULE[venue.type], f"{venue.type} bookings last at most {rule.max_duration_min} minutes"))
    opening = parse_hhmm(rules.bookable_hours.start)
    closing = parse_hhmm(rules.bookable_hours.end)
    same_day = request.start.date() == request.end.date() or (request.end.hour == 0 and request.end.minute == 0)
    if not same_day or minute_of_day(request.start) < opening or (minute_of_day(request.end) > closing and request.end.date() == request.start.date()):
        found.append(hard("P-HOURS", "BP-1.3", f"Venues can be booked only between {rules.bookable_hours.start} and {rules.bookable_hours.end}"))
    if request.attendees * 100 > venue.capacity * rules.fire_safety_cap_pct:
        found.append(hard("P-CAPACITY", "BP-4.1", f"{request.attendees} attendees exceed the capacity of {venue.code} ({venue.capacity})"))
    else:
        found.extend(venue_warnings(venue, request.attendees, rules))
    if venue.type == "lab":
        if request.requester_role != "admin" and request.requester_dept and request.requester_dept not in venue.eligible_depts:
            found.append(hard("P-ELIGIBILITY", "BP-3.1", f"{venue.code} is not open to the {request.requester_dept} department", "approver"))
        if venue.needs_supervisor and request.requester_role not in DEPT_ROLES and request.sponsor_id is None:
            found.append(hard("P-ELIGIBILITY", "BP-3.2", f"{venue.code} needs a faculty supervisor or sponsor"))
    return found


def guest_violations(request: BookingRequest, snapshot: Snapshot, rules: Rules, now: datetime, skip_lead: bool) -> list[Violation]:
    rule = rules.resources["guest_room"]
    found = timing_violations(request, rule.lead_time_hours, rule.max_advance_days, now, skip_lead)
    nights = nights_between(request.start, request.end)
    if nights < 1:
        found.append(hard("P-GUEST-STAY", "BP-5.3", "A stay needs at least one night"))
    if nights > rule.max_stay_nights:
        found.append(hard("P-GUEST-STAY", "BP-5.3", f"A stay may last at most {rule.max_stay_nights} nights"))
    if not request.host_ref and not request.meta.get("bundle_event"):
        found.append(hard("P-GUEST-LINK", "BP-7.1", "Guest nights must be linked to a host or an event"))
    room = next((r for r in snapshot.guest_rooms if r.id == request.resource_id), None)
    guests = request.meta.get("guests", request.attendees or 1)
    if room is not None and guests > room.capacity:
        found.append(hard("P-CAPACITY", "BP-5.6", f"Room {room.code} holds {room.capacity} guests, not {guests}"))
    return found


def parking_violations(request: BookingRequest, rules: Rules, now: datetime, skip_lead: bool) -> list[Violation]:
    rule = rules.resources["parking"]
    found = timing_violations(request, rule.lead_time_hours, rule.max_advance_days, now, skip_lead)
    if request.attendees and request.qty > request.attendees:
        found.append(hard("P-PARK-LIMIT", "BP-7.3", f"{request.qty} vehicles exceed {request.attendees} attendees"))
    return found


def check(request: BookingRequest, snapshot: Snapshot, rules: Rules, now: datetime, skip_lead: bool = False) -> list[Violation]:
    found: list[Violation] = []
    if request.requester_role == "student" and request.sponsor_id is None:
        found.append(hard("P-SPONSOR", "BP-1.2", "Student requests need a faculty sponsor"))
    if request.resource_type == "venue":
        found.extend(venue_violations(request, snapshot.venue(request.resource_id), rules, now, skip_lead))
    elif request.resource_type == "guest_room":
        found.extend(guest_violations(request, snapshot, rules, now, skip_lead))
    elif request.resource_type == "parking":
        found.extend(parking_violations(request, rules, now, skip_lead))
    return found


def hard_only(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.severity == "hard"]
