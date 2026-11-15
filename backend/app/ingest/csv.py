import csv
import io
import re

from rapidfuzz import fuzz

from app.ingest.types import Clarification, ParsedFile, RawRow

ALIASES = {
    "section": ["section", "class", "group", "sec", "batch"],
    "day": ["day", "weekday", "week day"],
    "start": ["start", "start time", "from", "begin"],
    "end": ["end", "end time", "to", "until", "finish"],
    "time": ["time", "slot", "period", "timing"],
    "code": ["course code", "code", "subject code", "paper code"],
    "name": ["course name", "course", "subject", "title", "paper"],
    "faculty": ["faculty", "teacher", "instructor", "professor", "prof", "lecturer"],
    "room": ["room", "venue", "hall", "location", "classroom"],
    "kind": ["type", "kind", "category", "mode"],
}
REQUIRED_GROUPS = [("section",), ("day",), ("code",), ("room",)]
MIN_SCORE = 80
CODE_LIKE = re.compile(r"^[A-Z]{2,3}\d[\dA-Z]{1,3}")


def alias_score(text: str, alias: str) -> float:
    if text == alias:
        return 100.0
    return fuzz.WRatio(text, alias) if len(text) > 3 else 0.0


def best_field(header: str) -> tuple[str, float]:
    text = header.strip().lower()
    scored = [(field, max(alias_score(text, alias) for alias in aliases)) for field, aliases in ALIASES.items()]
    return max(scored, key=lambda item: item[1])


def looks_like_codes(values: list[str]) -> bool:
    filled = [v for v in values if v.strip()]
    return bool(filled) and sum(1 for v in filled if CODE_LIKE.match(v.strip())) / len(filled) >= 0.8


def map_headers(headers: list[str], sample: list[list[str]], answers: dict[str, str]) -> tuple[dict[str, int], list[Clarification]]:
    candidates: list[tuple[float, str, int]] = []
    for position, header in enumerate(headers):
        field, score = best_field(header)
        if score >= MIN_SCORE:
            candidates.append((score, field, position))
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for score, field, position in sorted(candidates, key=lambda item: -item[0]):
        if field not in mapping and position not in used:
            mapping[field] = position
            used.add(position)
    if "code" not in mapping and "name" in mapping and looks_like_codes([row[mapping["name"]] for row in sample if len(row) > mapping["name"]]):
        mapping["code"] = mapping.pop("name")
    for field, header in ((key.split(":", 1)[1], value) for key, value in answers.items() if key.startswith("header:")):
        if header in headers:
            mapping[field] = headers.index(header)
            used.add(headers.index(header))
    clarifications: list[Clarification] = []
    needed = [group[0] for group in REQUIRED_GROUPS]
    if "time" not in mapping:
        needed += [f for f in ("start", "end") if f not in mapping]
    for field in needed:
        if field not in mapping:
            options = [h for i, h in enumerate(headers) if i not in used and h.strip()]
            clarifications.append(Clarification(f"header:{field}", f"Which column holds the {field.replace('code', 'course code')}?", options, field))
    return mapping, clarifications


def read_rows(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect) if any(cell.strip() for cell in row)]


def parse_csv(content: bytes, answers: dict[str, str] | None = None) -> ParsedFile:
    parsed = ParsedFile("csv")
    rows = read_rows(content)
    if len(rows) < 2:
        parsed.notes.append("The CSV has no data rows")
        return parsed
    headers = [h.strip() for h in rows[0]]
    mapping, parsed.clarifications = map_headers(headers, rows[1:6], answers or {})
    if parsed.clarifications:
        return parsed

    def cell(row: list[str], field: str) -> str:
        position = mapping.get(field)
        return row[position].strip() if position is not None and position < len(row) else ""

    for number, row in enumerate(rows[1:], start=2):
        start, end = cell(row, "start"), cell(row, "end")
        if "time" in mapping and not (start and end):
            match = re.search(r"(\d{1,2}[:.]\d{2})\s*(?:-|–|to)\s*(\d{1,2}[:.]\d{2})", cell(row, "time"))
            if match:
                start, end = match.group(1), match.group(2)
        parsed.rows.append(RawRow(
            section=cell(row, "section"), day=cell(row, "day"), start=start, end=end, code=cell(row, "code"), name=cell(row, "name"),
            faculty=cell(row, "faculty"), room=cell(row, "room"), kind=cell(row, "kind"), source=f"row {number}",
        ))
    return parsed
