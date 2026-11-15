import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.engine.timeutil import parse_hhmm
from app.ingest.cells import CODE_PATTERN, SECTION_TITLE
from app.ingest.types import Clarification, NormalisedEntry, RawRow

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
AUTO_ROOM_SCORE = 90
ASK_ROOM_SCORE = 70
LAB_CODE = re.compile(r"L\d$")


@dataclass
class Reference:
    sections: dict[tuple[str, int, str], int]
    section_sizes: dict[int, int]
    section_depts: dict[int, str]
    faculty: dict[int, tuple[str, str]]
    venues: dict[str, int]
    venue_types: dict[int, str]
    venue_capacity: dict[int, int]
    courses: dict[str, str]
    periods: list[list[str]]


@dataclass
class NormaliseResult:
    entries: list[NormalisedEntry] = field(default_factory=list)
    clarifications: list[Clarification] = field(default_factory=list)
    unknown_rooms: dict[str, list[str]] = field(default_factory=dict)
    unknown_courses: dict[str, list[str]] = field(default_factory=dict)


def parse_clock(text: str) -> int | None:
    value = text.strip().lower().replace(".", ":")
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", value)
    if not match:
        return None
    hours, minutes, suffix = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if suffix == "pm" and hours < 12:
        hours += 12
    if suffix == "am" and hours == 12:
        hours = 0
    return hours * 60 + minutes if hours < 24 and minutes < 60 else None


def parse_day(text: str) -> int | None:
    return DAYS.get(text.strip().lower()[:3])


def normalise_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def resolve_section(text: str, reference: Reference) -> int | None:
    match = SECTION_TITLE.search(text.strip())
    if not match:
        return None
    return reference.sections.get((match.group("dept").upper(), int(match.group("sem")), match.group("name").upper()))


def resolve_room(text: str, reference: Reference, answers: dict[str, str]) -> tuple[int | None, float, Clarification | None]:
    key = f"room:{text}"
    if key in answers:
        return reference.venues.get(normalise_key(answers[key])), 1.0, None
    exact = reference.venues.get(normalise_key(text))
    if exact is not None:
        return exact, 1.0, None
    match = process.extractOne(normalise_key(text), list(reference.venues), scorer=fuzz.ratio)
    if match and match[1] >= AUTO_ROOM_SCORE:
        return reference.venues[match[0]], match[1] / 100, None
    if match and match[1] >= ASK_ROOM_SCORE:
        options = [code for code, _, _ in process.extract(normalise_key(text), list(reference.venues), scorer=fuzz.ratio, limit=3)]
        return None, 0.0, Clarification(key, f"Which room is '{text}'?", options, "room")
    return None, 0.0, None


def resolve_faculty(text: str, section_id: int | None, reference: Reference, answers: dict[str, str]) -> tuple[int | None, float, Clarification | None]:
    if not text.strip():
        return None, 1.0, None
    key = f"faculty:{text}"
    names = {fid: name for fid, (name, _) in reference.faculty.items()}
    if key in answers:
        chosen = [fid for fid, name in names.items() if name == answers[key]]
        return (chosen[0] if chosen else None), 1.0, None
    wanted = normalise_key(text)
    exact = [fid for fid, name in names.items() if normalise_key(name) == wanted]
    candidates = exact or [fid for fid, name in names.items() if wanted and wanted in normalise_key(name)]
    if len(candidates) > 1 and section_id is not None:
        dept = reference.section_depts.get(section_id)
        same_dept = [fid for fid in candidates if reference.faculty[fid][1] == dept]
        if len(same_dept) == 1:
            return same_dept[0], 0.8, None
    if len(candidates) == 1:
        return candidates[0], 1.0 if exact else 0.85, None
    if len(candidates) > 1:
        options = [f"{names[fid]}" for fid in candidates]
        return None, 0.0, Clarification(key, f"Which faculty member is '{text}'?", sorted(set(options)), "faculty")
    return None, 0.0, None


def normalise_rows(rows: list[RawRow], reference: Reference, answers: dict[str, str] | None = None) -> NormaliseResult:
    answers = answers or {}
    result = NormaliseResult()
    asked: set[str] = set()
    for row in rows:
        section_id = resolve_section(row.section, reference)
        room_id, room_confidence, room_question = resolve_room(row.room, reference, answers) if row.room else (None, 0.0, None)
        faculty_id, faculty_confidence, faculty_question = resolve_faculty(row.faculty, section_id, reference, answers)
        for question in (room_question, faculty_question):
            if question and question.id not in asked:
                asked.add(question.id)
                result.clarifications.append(question)
        code = row.code.strip().upper()
        if row.room and room_id is None and room_question is None:
            result.unknown_rooms.setdefault(row.room, []).append(row.source)
        if code and code not in reference.courses and CODE_PATTERN.match(code) is not None:
            result.unknown_courses.setdefault(code, []).append(row.source)
        start, end = parse_clock(row.start), parse_clock(row.end)
        kind = (row.kind or "").lower()
        if kind not in ("lecture", "tutorial", "lab"):
            kind = "lab" if (room_id and reference.venue_types.get(room_id) == "lab") or LAB_CODE.search(code) else ("tutorial" if kind.startswith("tut") else "lecture")
        result.entries.append(NormalisedEntry(
            section_id=section_id, weekday=parse_day(row.day), start_min=start, end_min=end, course_code=code, course_name=reference.courses.get(code, row.name or code),
            faculty_id=faculty_id, venue_id=room_id, kind=kind, source=row.source, confidence=min(room_confidence or 0.0, faculty_confidence), room_text=row.room,
            faculty_text=row.faculty, section_text=row.section,
        ))
    return result


def build_reference(session) -> Reference:
    from sqlmodel import select

    from app.models import tables as t
    from app.rules import load_rules

    sections = list(session.exec(select(t.Section)))
    venues = list(session.exec(select(t.Venue)))
    return Reference(
        sections={(s.dept, s.semester, s.name): s.id for s in sections},
        section_sizes={s.id: s.size for s in sections}, section_depts={s.id: s.dept for s in sections},
        faculty={f.id: (f.name, f.dept) for f in session.exec(select(t.Faculty))},
        venues={normalise_key(v.code): v.id for v in venues}, venue_types={v.id: v.type for v in venues}, venue_capacity={v.id: v.capacity for v in venues},
        courses={c.code: c.name for c in session.exec(select(t.Course))}, periods=load_rules().periods,
    )


def period_edges(reference: Reference) -> tuple[set[int], set[int]]:
    return {parse_hhmm(a) for a, _ in reference.periods}, {parse_hhmm(b) for _, b in reference.periods}
