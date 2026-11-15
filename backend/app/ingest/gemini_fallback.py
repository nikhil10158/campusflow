from pydantic import BaseModel, ValidationError

from app.agent.llm import LLMUnavailable, get_llm
from app.ingest.types import RawRow

PROMPT = (
    "Extract every class from this synthetic university timetable PDF. Return JSON with a 'rows' list. "
    "Each row has: section (like 'CSE Sem 5 - Section A'), day (Mon..Sat), start (HH:MM), end (HH:MM), code, faculty, room, kind (lecture, tutorial or lab). "
    "Use only what is printed in the document and never invent classes."
)


class ExtractedRow(BaseModel):
    section: str
    day: str
    start: str
    end: str
    code: str
    faculty: str = ""
    room: str
    kind: str = "lecture"


class ExtractedTimetable(BaseModel):
    rows: list[ExtractedRow]


def extract_with_gemini(content: bytes) -> list[RawRow]:
    llm = get_llm()
    if not llm.usable():
        return []
    from google.genai import types

    contents = [types.Part.from_bytes(data=content, mime_type="application/pdf"), PROMPT]
    try:
        result = llm.generate(contents, response_schema=ExtractedTimetable.model_json_schema())
        extracted = ExtractedTimetable.model_validate_json(result.text)
    except (LLMUnavailable, ValidationError, ValueError):
        return []
    return [RawRow(section=r.section, day=r.day, start=r.start, end=r.end, code=r.code, faculty=r.faculty, room=r.room, kind=r.kind, source=f"AI row {n}") for n, r in enumerate(extracted.rows, start=1)]
