from collections import defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.ingest.normalise import NormaliseResult, Reference, normalise_key, period_edges
from app.ingest.types import Issue, NormalisedEntry


@dataclass(frozen=True)
class ExistingEntry:
    section_id: int
    weekday: int
    start_min: int
    end_min: int
    faculty_id: int | None
    venue_id: int
    course_code: str


def is_complete(entry: NormalisedEntry) -> bool:
    return None not in (entry.section_id, entry.weekday, entry.start_min, entry.end_min, entry.venue_id) and entry.end_min > entry.start_min


def overlapping(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def pair_conflicts(rows: list[tuple[bool, int, int, int, str]]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for position, first in enumerate(rows):
        for second in rows[position + 1:]:
            if not (first[0] or second[0]):
                continue
            if overlapping(first[1], first[2], second[1], second[2]):
                found.append((first[4], second[4]))
    return found


def validate(result: NormaliseResult, reference: Reference, existing: list[ExistingEntry]) -> list[Issue]:
    issues: list[Issue] = []
    entries = result.entries
    for entry in entries:
        if entry.section_id is None or entry.weekday is None or entry.start_min is None or entry.end_min is None or entry.end_min <= entry.start_min:
            issues.append(Issue("error", "INCOMPLETE_ROW", f"{entry.source}: section, day or time could not be read", [entry.source], "Fix the row so it names a known section, a weekday and a valid time range"))
    for room, sources in result.unknown_rooms.items():
        guess = process.extractOne(normalise_key(room), list(reference.venues), scorer=fuzz.ratio)
        hint = f" Did you mean {guess[0].upper()}?" if guess and guess[1] >= 50 else ""
        issues.append(Issue("error", "UNKNOWN_ROOM", f"Unknown room '{room}'", sources, f"Correct the room name or add the room to the campus list.{hint}"))
    for code, sources in result.unknown_courses.items():
        issues.append(Issue("warning", "UNKNOWN_COURSE", f"Course {code} is not in the course catalogue", sources, "Add the course to the catalogue or correct the code"))
    starts, ends = period_edges(reference)
    for entry in entries:
        if is_complete(entry) and (entry.start_min not in starts or entry.end_min not in ends):
            issues.append(Issue("warning", "OUTSIDE_PERIODS", f"{entry.source}: {entry.course_code} does not align with the timetable periods", [entry.source], "Move the class to start and end on period boundaries"))
        if is_complete(entry) and entry.kind != "lab":
            capacity = reference.venue_capacity.get(entry.venue_id, 0)
            size = reference.section_sizes.get(entry.section_id, 0)
            if capacity < size:
                issues.append(Issue("warning", "CAPACITY", f"{entry.source}: room seats {capacity} but section has {size} students", [entry.source], "Choose a larger room"))
    complete = [e for e in entries if is_complete(e)]
    venue_rows: dict[tuple[int, int], list[tuple[bool, int, int, int, str]]] = defaultdict(list)
    faculty_rows: dict[tuple[int, int], list[tuple[bool, int, int, int, str]]] = defaultdict(list)
    section_rows: dict[tuple[int, int], list[tuple[bool, int, int, int, str]]] = defaultdict(list)
    for entry in complete:
        label = f"{entry.source} {entry.course_code}"
        venue_rows[(entry.venue_id, entry.weekday)].append((True, entry.start_min, entry.end_min, 0, label))
        section_rows[(entry.section_id, entry.weekday)].append((True, entry.start_min, entry.end_min, 0, label))
        if entry.faculty_id is not None:
            faculty_rows[(entry.faculty_id, entry.weekday)].append((True, entry.start_min, entry.end_min, 0, label))
    for old in existing:
        label = f"existing {old.course_code} (section {old.section_id})"
        venue_rows[(old.venue_id, old.weekday)].append((False, old.start_min, old.end_min, 0, label))
        if old.faculty_id is not None:
            faculty_rows[(old.faculty_id, old.weekday)].append((False, old.start_min, old.end_min, 0, label))
    for (venue_id, weekday), rows in venue_rows.items():
        for first, second in pair_conflicts(rows):
            issues.append(Issue("error", "ROOM_DOUBLE_BOOKED", f"Room is used twice on weekday {weekday}: {first} and {second}", [first, second], "Move one of the classes to another free room"))
    for (faculty_id, weekday), rows in faculty_rows.items():
        name = reference.faculty[faculty_id][0]
        for first, second in pair_conflicts(rows):
            issues.append(Issue("error", "FACULTY_CONFLICT", f"{name} is in two places at once: {first} and {second}", [first, second], "Reassign one class or move it to another period"))
    for (section_id, weekday), rows in section_rows.items():
        for first, second in pair_conflicts(rows):
            issues.append(Issue("error", "SECTION_OVERLAP", f"Section has two classes at the same time: {first} and {second}", [first, second], "Remove the duplicate or change one of the times"))
    return issues

