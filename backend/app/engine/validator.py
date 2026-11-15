from collections import defaultdict
from datetime import date, datetime, timedelta

from app.engine.types import BookingInfo, Snapshot, Violation
from app.rules import Rules

ResourceKey = tuple[str, int]


def violation(code: str, rule_id: str, message: str) -> Violation:
    return Violation(code, rule_id, "hard", message, "admin")


def span_minutes(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60


def class_occurrences(snapshot: Snapshot, venue_id: int, first_day: date, last_day: date) -> list[tuple[datetime, datetime, str]]:
    cancelled = {
        (exc.entry_id, exc.date)
        for exc in snapshot.exceptions
        if exc.status == "APPROVED" and exc.type in ("cancelled", "released", "moved")
    }
    found: list[tuple[datetime, datetime, str]] = []
    day = first_day
    while day <= last_day:
        if day not in snapshot.holidays:
            midnight = datetime(day.year, day.month, day.day)
            for entry in snapshot.entries:
                if entry.venue_id == venue_id and entry.weekday == day.weekday() and entry.effective_from <= day <= entry.effective_to:
                    if (entry.id, day) not in cancelled:
                        found.append((midnight + timedelta(minutes=entry.start_min), midnight + timedelta(minutes=entry.end_min), entry.course_code))
            for exc in snapshot.exceptions:
                if exc.status == "APPROVED" and exc.type in ("moved", "extra") and exc.venue_id == venue_id and exc.date == day:
                    if exc.start_min is not None and exc.end_min is not None:
                        found.append((midnight + timedelta(minutes=exc.start_min), midnight + timedelta(minutes=exc.end_min), "extra class"))
        day += timedelta(days=1)
    return found


def confirmed(snapshot: Snapshot, resource_type: str) -> list[BookingInfo]:
    return [b for b in snapshot.bookings if b.status == "CONFIRMED" and b.resource_type == resource_type]


def check_venues(snapshot: Snapshot, rules: Rules, only: set[ResourceKey] | None) -> list[Violation]:
    found: list[Violation] = []
    by_venue: dict[int, list[BookingInfo]] = defaultdict(list)
    for booking in confirmed(snapshot, "venue"):
        if only is None or ("venue", booking.resource_id) in only:
            by_venue[booking.resource_id].append(booking)
    venues = snapshot.venues_by_id()
    for venue_id, bookings in by_venue.items():
        venue = venues[venue_id]
        bookings.sort(key=lambda b: b.start_dt)
        for booking in bookings:
            if booking.attendees * 100 > venue.capacity * rules.fire_safety_cap_pct:
                found.append(violation("H-VENUE-CAPACITY", "BP-4.1", f"Booking #{booking.id} has {booking.attendees} attendees in {venue.code} (capacity {venue.capacity})"))
            padded_start = booking.start_dt - timedelta(minutes=venue.setup_buffer_min)
            padded_end = booking.end_dt + timedelta(minutes=venue.teardown_buffer_min)
            for start, end, label in class_occurrences(snapshot, venue_id, padded_start.date(), padded_end.date()):
                if start < padded_end and padded_start < end:
                    code = "H-VENUE-OVERLAP" if start < booking.end_dt and booking.start_dt < end else "H-BUFFER"
                    found.append(violation(code, "BP-2.1", f"Booking #{booking.id} clashes with {label} in {venue.code}"))
            for block in snapshot.maintenance:
                if block.resource_type == "venue" and block.resource_id == venue_id and block.start_dt < booking.end_dt and booking.start_dt < block.end_dt:
                    found.append(violation("H-VENUE-OVERLAP", "BP-2.1", f"Booking #{booking.id} overlaps maintenance in {venue.code}"))
        gap_needed = min(venue.setup_buffer_min, venue.teardown_buffer_min)
        for position, first in enumerate(bookings):
            for second in bookings[position + 1:]:
                gap = span_minutes(first.end_dt, second.start_dt)
                if gap >= gap_needed:
                    break
                if gap < 0:
                    found.append(violation("H-VENUE-OVERLAP", "BP-2.1", f"Bookings #{first.id} and #{second.id} overlap in {venue.code}"))
                else:
                    found.append(violation("H-BUFFER", "BP-4.3", f"Bookings #{first.id} and #{second.id} leave less than {gap_needed} minutes in {venue.code}"))
    return found


def check_guest_rooms(snapshot: Snapshot, rules: Rules, only: set[ResourceKey] | None) -> list[Violation]:
    found: list[Violation] = []
    turnover = timedelta(minutes=rules.resources["guest_room"].turnover_buffer_min)
    by_room: dict[int, list[BookingInfo]] = defaultdict(list)
    for booking in confirmed(snapshot, "guest_room"):
        if only is None or ("guest_room", booking.resource_id) in only:
            by_room[booking.resource_id].append(booking)
    for room_id, bookings in by_room.items():
        bookings.sort(key=lambda b: b.start_dt)
        for first, second in zip(bookings, bookings[1:]):
            if second.start_dt < first.end_dt + turnover:
                found.append(violation("H-GUEST-OVERLAP", "BP-5.4", f"Guest bookings #{first.id} and #{second.id} clash in room {room_id}"))
    return found


def vehicles_of(booking: BookingInfo) -> dict[str, int]:
    vehicles = booking.meta.get("vehicles")
    return dict(vehicles) if vehicles else {"car": booking.qty}


def capacity_of(lot_cap: dict[str, int], vehicle: str) -> int:
    return lot_cap.get(vehicle, 0)


def check_parking(snapshot: Snapshot, rules: Rules, only: set[ResourceKey] | None) -> list[Violation]:
    found: list[Violation] = []
    lots = {lot.id: lot for lot in snapshot.lots}
    events: dict[tuple[int, str], list[tuple[datetime, int]]] = defaultdict(list)
    for booking in confirmed(snapshot, "parking"):
        if only is not None and ("parking", booking.resource_id) not in only:
            continue
        for vehicle, count in vehicles_of(booking).items():
            events[(booking.resource_id, vehicle)].append((booking.start_dt, count))
            events[(booking.resource_id, vehicle)].append((booking.end_dt, -count))
    for (lot_id, vehicle), changes in events.items():
        lot = lots[lot_id]
        raw = {"car": lot.cap_car, "bike": lot.cap_bike, "bus": lot.cap_bus, "ev": lot.ev_bays, "vip": lot.vip_bays}
        limit = raw.get(vehicle, 0) * (100 - rules.walkin_reserve_pct) // 100
        changes.sort(key=lambda change: (change[0], change[1]))
        running = 0
        for moment, delta in changes:
            running += delta
            if running > limit:
                found.append(violation("H-PARK-OVERCAP", "BP-6.4", f"Lot {lot.name} holds {running} {vehicle} vehicles at {moment:%d %b %H:%M}, limit {limit}"))
                break
    return found


def check_bundles(snapshot: Snapshot) -> list[Violation]:
    found: list[Violation] = []
    grouped: dict[int, list[BookingInfo]] = defaultdict(list)
    for booking in snapshot.bookings:
        if booking.bundle_id is not None and booking.status in ("CONFIRMED", "HELD"):
            grouped[booking.bundle_id].append(booking)
    for bundle_id, parts in grouped.items():
        venues = [p for p in parts if p.resource_type == "venue"]
        if not venues:
            continue
        event_start = min(p.start_dt for p in venues)
        event_end = max(p.end_dt for p in venues)
        for part in parts:
            if part.resource_type == "guest_room" and not (part.start_dt.date() <= event_start.date() and part.end_dt.date() >= event_end.date()):
                found.append(violation("H-BUNDLE-WINDOW", "BP-7.2", f"Guest nights of booking #{part.id} do not cover the event of bundle {bundle_id}"))
            if part.resource_type == "parking" and not (part.start_dt <= event_start and part.end_dt >= event_end):
                found.append(violation("H-BUNDLE-WINDOW", "BP-7.2", f"Parking of booking #{part.id} does not cover the event of bundle {bundle_id}"))
    return found


def check_approvals(snapshot: Snapshot) -> list[Violation]:
    found: list[Violation] = []
    steps: dict[int, list[str]] = defaultdict(list)
    for step in snapshot.steps:
        steps[step.booking_id].append(step.status)
    for booking in snapshot.bookings:
        if booking.status == "CONFIRMED":
            statuses = steps.get(booking.id, [])
            if not statuses or any(s != "APPROVED" for s in statuses):
                found.append(violation("H-APPROVAL-MISSING", "BP-8.2", f"Confirmed booking #{booking.id} lacks approved steps"))
    return found


def check_passes(snapshot: Snapshot) -> list[Violation]:
    found: list[Violation] = []
    status = {b.id: b.status for b in snapshot.bookings}
    for issued in snapshot.passes:
        if not issued.revoked and status.get(issued.booking_id) != "CONFIRMED":
            found.append(violation("H-PASS-ORPHAN", "BP-6.5", f"Pass #{issued.id} belongs to a booking that is not confirmed"))
    return found


def check_policy_limits(snapshot: Snapshot, rules: Rules, only: set[ResourceKey] | None) -> list[Violation]:
    found: list[Violation] = []
    venues = snapshot.venues_by_id()
    opening = rules.bookable_hours.start
    closing = rules.bookable_hours.end
    for booking in snapshot.bookings:
        if booking.status != "CONFIRMED" or (only is not None and (booking.resource_type, booking.resource_id) not in only):
            continue
        if booking.resource_type == "venue":
            venue = venues[booking.resource_id]
            limit = rules.for_venue_type(venue.type).max_duration_min
            outside = booking.start_dt.strftime("%H:%M") < opening or booking.end_dt.strftime("%H:%M") > closing or booking.end_dt.date() != booking.start_dt.date()
            if span_minutes(booking.start_dt, booking.end_dt) > limit or outside:
                found.append(violation("H-POLICY-HARD", "BP-1.3", f"Booking #{booking.id} breaks duration or hours rules"))
        if booking.resource_type == "guest_room":
            nights = (booking.end_dt.date() - booking.start_dt.date()).days
            if nights > rules.resources["guest_room"].max_stay_nights:
                found.append(violation("H-POLICY-HARD", "BP-5.3", f"Booking #{booking.id} stays {nights} nights"))
        if booking.resource_type == "parking" and booking.attendees and sum(vehicles_of(booking).values()) > booking.attendees:
            found.append(violation("H-POLICY-HARD", "BP-7.3", f"Booking #{booking.id} parks more vehicles than attendees"))
    return found


def validate(snapshot: Snapshot, rules: Rules, only: set[ResourceKey] | None = None) -> list[Violation]:
    found = check_venues(snapshot, rules, only)
    found += check_guest_rooms(snapshot, rules, only)
    found += check_parking(snapshot, rules, only)
    found += check_policy_limits(snapshot, rules, only)
    if only is None:
        found += check_bundles(snapshot)
        found += check_approvals(snapshot)
        found += check_passes(snapshot)
    return found
