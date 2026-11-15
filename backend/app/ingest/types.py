from dataclasses import asdict, dataclass, field


@dataclass
class RawRow:
    section: str = ""
    day: str = ""
    start: str = ""
    end: str = ""
    code: str = ""
    name: str = ""
    faculty: str = ""
    room: str = ""
    kind: str = ""
    source: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Clarification:
    id: str
    question: str
    options: list[str]
    field: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedFile:
    format: str
    rows: list[RawRow] = field(default_factory=list)
    clarifications: list[Clarification] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ai_extracted: bool = False


@dataclass
class NormalisedEntry:
    section_id: int | None
    weekday: int | None
    start_min: int | None
    end_min: int | None
    course_code: str
    course_name: str
    faculty_id: int | None
    venue_id: int | None
    kind: str
    source: str
    confidence: float = 1.0
    room_text: str = ""
    faculty_text: str = ""
    section_text: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    def key(self) -> tuple:
        return (self.section_id, self.weekday, self.start_min, self.end_min, self.course_code, self.faculty_id, self.venue_id, self.kind)


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    sources: list[str] = field(default_factory=list)
    suggested_fix: str = ""

    def as_dict(self) -> dict:
        return asdict(self)
