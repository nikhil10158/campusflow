from datetime import date, datetime, timedelta

from app.engine.types import Snapshot


def rounded_interval(start_min: int, end_min: int, setup: int = 0, teardown: int = 0) -> tuple[int, int]:
    low = max(0, ((start_min - setup) // 15) * 15)
    high = min(1440, -(-(end_min + teardown) // 15) * 15)
    return low, high


def minutes_on_day(start: datetime, end: datetime, day: date) -> tuple[int, int] | None:
    day_start = datetime(day.year, day.month, day.day)
    day_end = day_start + timedelta(days=1)
    clipped_start = max(start, day_start)
    clipped_end = min(end, day_end)
    if clipped_end <= clipped_start:
        return None
    return int((clipped_start - day_start).total_seconds() // 60), int((clipped_end - day_start).total_seconds() // 60)


def crosses(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def cleared_dates(snapshot: Snapshot, entry_id: int) -> set[date]:
    return {
        exc.date
        for exc in snapshot.exceptions
        if exc.entry_id == entry_id and exc.status == "APPROVED" and exc.type in ("cancelled", "released", "moved")
    }


def busy_intervals(snapshot: Snapshot, venue_id: int, day: date) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for entry in snapshot.entries:
        if entry.venue_id != venue_id or entry.weekday != day.weekday():
            continue
        if not (entry.effective_from <= day <= entry.effective_to):
            continue
        if day in snapshot.holidays or day in cleared_dates(snapshot, entry.id):
            continue
        found.append(rounded_interval(entry.start_min, entry.end_min))
    for exc in snapshot.exceptions:
        if exc.status == "APPROVED" and exc.type in ("moved", "extra") and exc.venue_id == venue_id and exc.date == day:
            if exc.start_min is not None and exc.end_min is not None:
                found.append(rounded_interval(exc.start_min, exc.end_min))
    for booking in snapshot.bookings:
        if booking.resource_type != "venue" or booking.resource_id != venue_id:
            continue
        active = booking.status == "CONFIRMED" or (
            booking.status == "HELD" and (booking.hold_expires_at is None or booking.hold_expires_at > snapshot.now)
        )
        span = minutes_on_day(booking.start_dt, booking.end_dt, day) if active else None
        if span:
            found.append(rounded_interval(*span))
    for block in snapshot.maintenance:
        if block.resource_type == "venue" and block.resource_id == venue_id:
            span = minutes_on_day(block.start_dt, block.end_dt, day)
            if span:
                found.append(rounded_interval(*span))
    return found


def released_intervals(snapshot: Snapshot, venue_id: int, day: date) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for entry in snapshot.entries:
        if entry.venue_id != venue_id or entry.weekday != day.weekday():
            continue
        if entry.effective_from <= day <= entry.effective_to and day not in snapshot.holidays and day in cleared_dates(snapshot, entry.id):
            found.append(rounded_interval(entry.start_min, entry.end_min))
    return found


def window_state(snapshot: Snapshot, venue_id: int, start: datetime, end: datetime) -> str:
    venue = snapshot.venue(venue_id)
    if not venue.bookable:
        return "BUSY"
    released = False
    day = start.date()
    last_day = (end - timedelta(microseconds=1)).date()
    while day <= last_day:
        span = minutes_on_day(start, end, day)
        if span:
            setup = venue.setup_buffer_min if day == start.date() else 0
            teardown = venue.teardown_buffer_min if day == last_day else 0
            wanted = rounded_interval(span[0], span[1], setup, teardown)
            if any(crosses(wanted, busy) for busy in busy_intervals(snapshot, venue_id, day)):
                return "BUSY"
            if any(crosses(wanted, rel) for rel in released_intervals(snapshot, venue_id, day)):
                released = True
        day += timedelta(days=1)
    return "FREE_RELEASED" if released else "FREE"


def free_states(snapshot: Snapshot, windows: list[tuple[datetime, datetime]], venue_ids: list[int]) -> dict[int, str]:
    result: dict[int, str] = {}
    for venue_id in venue_ids:
        states = [window_state(snapshot, venue_id, start, end) for start, end in windows]
        if "BUSY" in states:
            continue
        result[venue_id] = "FREE_RELEASED" if "FREE_RELEASED" in states else "FREE"
    return result
