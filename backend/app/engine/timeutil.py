from collections.abc import Iterator
from datetime import date, datetime, timedelta

SLOT_MINUTES = 15
SLOTS_PER_DAY = 96
MINUTES_PER_DAY = 1440


def floor_slot(minute: int) -> int:
    return minute // SLOT_MINUTES


def ceil_slot(minute: int) -> int:
    return -(-minute // SLOT_MINUTES)


def minute_of_day(moment: datetime) -> int:
    return moment.hour * 60 + moment.minute


def parse_hhmm(text: str) -> int:
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def format_minute(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def at_minute(day: date, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day) + timedelta(minutes=minute)


def date_range(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def slot_bounds(start_min: int, end_min: int, setup_min: int = 0, teardown_min: int = 0) -> tuple[int, int]:
    low = max(0, floor_slot(start_min - setup_min))
    high = min(SLOTS_PER_DAY, ceil_slot(end_min + teardown_min))
    return low, high


def day_pieces(start: datetime, end: datetime, setup_min: int = 0, teardown_min: int = 0) -> Iterator[tuple[date, int, int]]:
    if end <= start:
        return
    current = start.date()
    last = (end - timedelta(microseconds=1)).date()
    while current <= last:
        day_start = at_minute(current, 0)
        piece_start = max(start, day_start)
        piece_end = min(end, day_start + timedelta(days=1))
        start_min = int((piece_start - day_start).total_seconds() // 60)
        end_min = int((piece_end - day_start).total_seconds() // 60)
        low, high = slot_bounds(
            start_min,
            end_min,
            setup_min if current == start.date() else 0,
            teardown_min if current == last else 0,
        )
        yield current, low, high
        current += timedelta(days=1)


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def nights_between(start: datetime, end: datetime) -> int:
    return (end.date() - start.date()).days
