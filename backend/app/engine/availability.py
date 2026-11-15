from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from app.engine.timeutil import SLOTS_PER_DAY, ceil_slot, date_range, day_pieces, floor_slot, parse_hhmm
from app.engine.types import BookingInfo, EntryInfo, ExceptionInfo, Segment, Snapshot
from app.rules import load_rules

TIMETABLE, CONFIRMED, HELD, MAINTENANCE, RELEASED = range(5)
LAYER_NAMES = ("timetable", "confirmed", "held", "maintenance")
CLEARING_EXCEPTIONS = ("cancelled", "released", "moved")
SATURDAY_PERIODS = 4


def build_teaching_masks() -> tuple[np.ndarray, np.ndarray]:
    weekday_mask = np.zeros(SLOTS_PER_DAY, dtype=bool)
    saturday_mask = np.zeros(SLOTS_PER_DAY, dtype=bool)
    for number, (start, end) in enumerate(load_rules().periods):
        low = floor_slot(parse_hhmm(start))
        high = ceil_slot(parse_hhmm(end))
        weekday_mask[low:high] = True
        if number < SATURDAY_PERIODS:
            saturday_mask[low:high] = True
    return weekday_mask, saturday_mask


TEACHING_MASKS = build_teaching_masks()


@dataclass
class Availability:
    state: str
    blockers: list[Segment] = field(default_factory=list)

    @property
    def free(self) -> bool:
        return self.state in ("FREE", "FREE_RELEASED")


def section_label(snapshot: Snapshot, section_id: int) -> str:
    section = snapshot.sections.get(section_id)
    if section is None:
        return f"section {section_id}"
    return f"{section.dept} Sem {section.semester}-{section.name}"


def entry_label(snapshot: Snapshot, entry: EntryInfo) -> str:
    faculty = snapshot.faculty.get(entry.faculty_id, "") if entry.faculty_id else ""
    parts = [entry.course_code, section_label(snapshot, entry.section_id)]
    if faculty:
        parts.append(faculty)
    return ", ".join(parts)


def booking_is_active(booking: BookingInfo, now: datetime) -> bool:
    if booking.status == "CONFIRMED":
        return True
    if booking.status == "HELD":
        return booking.hold_expires_at is None or booking.hold_expires_at > now
    return False


class AvailabilityIndex:
    def __init__(self, snapshot: Snapshot, start: date, end: date) -> None:
        self.snapshot = snapshot
        self.start = start
        self.end = end
        self.days = (end - start).days + 1
        self.venue_pos = {venue.id: position for position, venue in enumerate(snapshot.venues)}
        self.layers = np.zeros((len(snapshot.venues), self.days, 5, SLOTS_PER_DAY), dtype=bool)
        self.segments: dict[tuple[int, int], list[Segment]] = defaultdict(list)
        self.build()
        self.busy = self.layers[:, :, :4, :].any(axis=2)

    def covers(self, start: datetime, end: datetime) -> bool:
        return start.date() >= self.start and (end - timedelta(microseconds=1)).date() <= self.end

    def offset(self, day: date) -> int | None:
        position = (day - self.start).days
        return position if 0 <= position < self.days else None

    def mark(self, venue_id: int, day: date, layer: int, low: int, high: int, label: str, source_id: int | None, ghost: bool = False) -> None:
        position = self.venue_pos.get(venue_id)
        offset = self.offset(day)
        if position is None or offset is None or high <= low:
            return
        self.layers[position, offset, layer, low:high] = True
        if layer != RELEASED:
            self.segments[(venue_id, offset)].append(Segment(low, high, LAYER_NAMES[layer], label, source_id, ghost))

    def build(self) -> None:
        snapshot = self.snapshot
        cleared = self.build_exception_map()
        for entry in snapshot.entries:
            self.expand_entry(entry, cleared)
        for exception in snapshot.exceptions:
            if exception.status == "APPROVED" and exception.type in ("moved", "extra"):
                self.expand_extra(exception)
        for booking in snapshot.bookings:
            if booking.resource_type == "venue" and booking_is_active(booking, snapshot.now):
                layer = CONFIRMED if booking.status == "CONFIRMED" else HELD
                label = f"{booking.event_title} (booking #{booking.id}, {booking.status.lower()})"
                for day, low, high in day_pieces(booking.start_dt, booking.end_dt):
                    self.mark(booking.resource_id, day, layer, low, high, label, booking.id)
        for block in snapshot.maintenance:
            if block.resource_type == "venue":
                for day, low, high in day_pieces(block.start_dt, block.end_dt):
                    self.mark(block.resource_id, day, MAINTENANCE, low, high, f"Maintenance: {block.reason}", block.id)
        for segments in self.segments.values():
            segments.sort(key=lambda segment: segment.start_slot)

    def build_exception_map(self) -> dict[tuple[int, date], ExceptionInfo]:
        cleared: dict[tuple[int, date], ExceptionInfo] = {}
        for exception in self.snapshot.exceptions:
            if exception.status == "APPROVED" and exception.type in CLEARING_EXCEPTIONS:
                cleared[(exception.entry_id, exception.date)] = exception
        return cleared

    def expand_entry(self, entry: EntryInfo, cleared: dict[tuple[int, date], ExceptionInfo]) -> None:
        first = max(entry.effective_from, self.start)
        last = min(entry.effective_to, self.end)
        if first > last:
            return
        day = first + timedelta(days=(entry.weekday - first.weekday()) % 7)
        low = floor_slot(entry.start_min)
        high = ceil_slot(entry.end_min)
        label = entry_label(self.snapshot, entry)
        ghost = entry.id in self.snapshot.ghost_entry_ids
        while day <= last:
            if day not in self.snapshot.holidays:
                if (entry.id, day) in cleared:
                    self.mark(entry.venue_id, day, RELEASED, low, high, label, entry.id)
                else:
                    self.mark(entry.venue_id, day, TIMETABLE, low, high, label, entry.id, ghost)
            day += timedelta(days=7)

    def expand_extra(self, exception: ExceptionInfo) -> None:
        if exception.venue_id is None or exception.start_min is None or exception.end_min is None:
            return
        entry = self.snapshot.entry(exception.entry_id)
        course = entry.course_code if entry else "class"
        label = f"{'Moved' if exception.type == 'moved' else 'Extra'} {course} (exception #{exception.id})"
        self.mark(exception.venue_id, exception.date, TIMETABLE, floor_slot(exception.start_min), ceil_slot(exception.end_min), label, exception.id)

    def pieces(self, venue_id: int, start: datetime, end: datetime, with_buffers: bool) -> list[tuple[int, int, int]]:
        venue = self.snapshot.venue(venue_id)
        setup = venue.setup_buffer_min if with_buffers else 0
        teardown = venue.teardown_buffer_min if with_buffers else 0
        result: list[tuple[int, int, int]] = []
        for day, low, high in day_pieces(start, end, setup, teardown):
            offset = self.offset(day)
            if offset is None:
                raise ValueError(f"{day} is outside the availability index range")
            result.append((offset, low, high))
        return result

    def is_free(self, venue_id: int, start: datetime, end: datetime, with_buffers: bool = True) -> bool:
        venue = self.snapshot.venue(venue_id)
        if not venue.bookable:
            return False
        position = self.venue_pos[venue_id]
        return not any(self.busy[position, offset, low:high].any() for offset, low, high in self.pieces(venue_id, start, end, with_buffers))

    def check(self, venue_id: int, start: datetime, end: datetime, with_buffers: bool = True) -> Availability:
        venue = self.snapshot.venue(venue_id)
        if not venue.bookable:
            return Availability("BUSY", [Segment(0, SLOTS_PER_DAY, "maintenance", f"{venue.code} is not bookable")])
        position = self.venue_pos[venue_id]
        blockers: list[Segment] = []
        released = False
        for offset, low, high in self.pieces(venue_id, start, end, with_buffers):
            for segment in self.segments.get((venue_id, offset), []):
                if segment.start_slot < high and low < segment.end_slot:
                    blockers.append(segment)
            if self.layers[position, offset, RELEASED, low:high].any():
                released = True
        if blockers:
            return Availability("BUSY", blockers)
        return Availability("FREE_RELEASED" if released else "FREE")

    def busy_reasons(self, venue_id: int, start: datetime, end: datetime) -> list[Segment]:
        return self.check(venue_id, start, end).blockers

    def free_windows(self, venue_id: int, day: date, min_minutes: int, first_minute: int = 420, last_minute: int = 1320) -> list[tuple[int, int]]:
        offset = self.offset(day)
        if offset is None:
            raise ValueError(f"{day} is outside the availability index range")
        row = self.busy[self.venue_pos[venue_id], offset]
        windows: list[tuple[int, int]] = []
        run_start: int | None = None
        for slot in range(first_minute // 15, last_minute // 15 + 1):
            is_busy = slot >= last_minute // 15 or bool(row[slot])
            if not is_busy and run_start is None:
                run_start = slot
            if is_busy and run_start is not None:
                if (slot - run_start) * 15 >= min_minutes:
                    windows.append((run_start * 15, slot * 15))
                run_start = None
        return windows

    def day_segments(self, venue_id: int, day: date) -> list[Segment]:
        offset = self.offset(day)
        return list(self.segments.get((venue_id, offset), [])) if offset is not None else []

    def utilisation(self, venue_id: int, start: date, end: date, timetable_only: bool = False) -> float:
        position = self.venue_pos[venue_id]
        used = 0
        total = 0
        for day in date_range(max(start, self.start), min(end, self.end)):
            if day.weekday() == 6 or day in self.snapshot.holidays:
                continue
            offset = self.offset(day)
            if offset is None:
                continue
            mask = TEACHING_MASKS[min(day.weekday(), 5) == 5]
            source = self.layers[position, offset, TIMETABLE] if timetable_only else self.busy[position, offset]
            used += int(source[mask].sum())
            total += int(mask.sum())
        return used / total if total else 0.0
