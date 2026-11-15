import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from rapidfuzz import fuzz, process

MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DEPTS = ["CSE", "ECE", "ME", "CHE", "EEE"]
INJECTION = re.compile(
    r"ignore (all |any |the )?(previous|prior|above|earlier)|disregard (the )?(rules|instructions|policy|policies)|system prompt|reveal your|you are now|developer mode|"
    r"approve (all|every|the pending)|confirm (all|every)|submit (the )?booking for me without|call (the )?(submit|approve|confirm|import|issue)|bypass|override (the )?(policy|rules|approval)",
    re.IGNORECASE,
)
DATE_RANGE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|—|to)\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})\b", re.IGNORECASE)
DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTHS})(?:\s+(\d{{4}}))?\b", re.IGNORECASE)
MONTH_DAY = re.compile(rf"\b({MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{{4}}))?\b", re.IGNORECASE)
TIME_RANGE = re.compile(r"(?<![\d:])(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:-|–|—|to|until|till)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?![\d:])", re.IGNORECASE)
SINGLE_TIME = re.compile(r"\b(?:at|from|around|starting)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.IGNORECASE)
WEEKDAY_RANGE = re.compile(r"\b(mon|tue|wed|thu|fri|sat)[a-z]*\s*(?:-|–|—|to|and)\s*(mon|tue|wed|thu|fri|sat)[a-z]*\b", re.IGNORECASE)
WEEKDAY = re.compile(r"\b(next\s+|this\s+|coming\s+)?(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b", re.IGNORECASE)
VENUE_CODE = re.compile(r"\b(AMP|SH|L|[ABC])\s*-?\s*(\d{1,3})\b", re.IGNORECASE)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


@dataclass
class Intent:
    kind: str
    params: dict = field(default_factory=dict)
    clarify: dict | None = None
    note: str = ""
    original: str = ""


def is_injection(text: str) -> bool:
    return bool(INJECTION.search(text))


def word_to_number(text: str) -> str:
    return re.sub(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", lambda m: str(NUMBER_WORDS[m.group(1).lower()]), text, flags=re.IGNORECASE)


def month_number(name: str) -> int:
    return datetime.strptime(name[:3].title(), "%b").month


def make_date(day: int, month: int, now: datetime, year: int | None = None) -> date | None:
    try:
        candidate = date(year or now.year, month, day)
    except ValueError:
        return None
    if year is None and candidate < now.date() - timedelta(days=1):
        candidate = date(now.year + 1, month, day)
    return candidate


def next_weekday(weekday: int, now: datetime, force_next: bool) -> date:
    delta = (weekday - now.weekday()) % 7
    if delta == 0 and force_next:
        delta = 7
    if force_next and delta < 7 and weekday <= now.weekday():
        delta += 7
    return now.date() + timedelta(days=delta)


def extract_dates(text: str, now: datetime) -> tuple[list[date], str]:
    found: list[date] = []
    remaining = text
    match = DATE_RANGE.search(remaining)
    if match:
        month = month_number(match.group(3))
        first, last = int(match.group(1)), int(match.group(2))
        found += [d for d in (make_date(day, month, now) for day in range(first, last + 1)) if d]
        remaining = remaining[: match.start()] + " " + remaining[match.end():]
    for pattern, day_group, month_group, year_group in ((DAY_MONTH, 1, 2, 3), (MONTH_DAY, 2, 1, 3)):
        for match in list(pattern.finditer(remaining)):
            year = int(match.group(year_group)) if match.group(year_group) else None
            parsed = make_date(int(match.group(day_group)), month_number(match.group(month_group)), now, year)
            if parsed:
                found.append(parsed)
        remaining = pattern.sub(" ", remaining)
    iso = re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", remaining)
    for year, month, day in iso:
        found.append(date(int(year), int(month), int(day)))
    remaining = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", remaining)
    lower = remaining.lower()
    if "day after tomorrow" in lower:
        found.append(now.date() + timedelta(days=2))
    elif "tomorrow" in lower:
        found.append(now.date() + timedelta(days=1))
    elif re.search(r"\btoday\b|\btonight\b", lower):
        found.append(now.date())
    if not found and re.search(r"\bnext week\b", lower):
        monday = now.date() + timedelta(days=7 - now.weekday())
        found += [monday + timedelta(days=n) for n in range(5)]
    elif not found and re.search(r"\bthis week\b", lower):
        found += [now.date() + timedelta(days=n) for n in range(0, 5 - now.weekday())] if now.weekday() < 5 else []
    if not found:
        span = WEEKDAY_RANGE.search(remaining)
        if span:
            first, last = WEEKDAYS[span.group(1).lower()[:3]], WEEKDAYS[span.group(2).lower()[:3]]
            start = next_weekday(first, now, force_next=False)
            found += [start + timedelta(days=n) for n in range(0, (last - first) % 7 + 1)]
        else:
            for match in WEEKDAY.finditer(remaining):
                found.append(next_weekday(WEEKDAYS[match.group(2).lower()[:3]], now, force_next=bool(match.group(1) and match.group(1).strip().lower() in ("next", "coming"))))
    return sorted(set(found)), remaining


def to_minutes(hour: int, minute: int, meridiem: str | None) -> int:
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return hour * 60 + minute


def extract_times(text: str) -> tuple[int | None, int | None, str]:
    match = TIME_RANGE.search(text)
    if match:
        first_hour, first_minute = int(match.group(1)), int(match.group(2) or 0)
        last_hour, last_minute = int(match.group(4)), int(match.group(5) or 0)
        first_meridiem, last_meridiem = (match.group(3) or "").lower() or None, (match.group(6) or "").lower() or None
        if first_hour <= 24 and last_hour <= 24:
            if first_meridiem and not last_meridiem:
                last_meridiem = first_meridiem
            if last_meridiem and not first_meridiem:
                first_meridiem = last_meridiem
                if to_minutes(first_hour, first_minute, first_meridiem) >= to_minutes(last_hour, last_minute, last_meridiem):
                    first_meridiem = "am" if last_meridiem == "pm" else "pm"
            start = to_minutes(first_hour, first_minute, first_meridiem)
            end = to_minutes(last_hour, last_minute, last_meridiem)
            if first_meridiem and end <= start and last_hour <= 12:
                end += 12 * 60
            if not first_meridiem and not last_meridiem:
                if first_hour < 7:
                    start += 12 * 60
                if last_hour < 7:
                    end += 12 * 60
                if end <= start and last_hour < 12:
                    end += 12 * 60
            if end > start:
                return start, end, text[: match.start()] + " " + text[match.end():]
    single = SINGLE_TIME.search(text)
    if single:
        start = to_minutes(int(single.group(1)), int(single.group(2) or 0), (single.group(3) or "").lower() or None)
        if not single.group(3) and start < 7 * 60:
            start += 12 * 60
        return start, None, text[: single.start()] + " " + text[single.end():]
    return None, None, text


def extract_duration(text: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?\s*(hour|hr|hrs|h)\b", text, re.IGNORECASE)
    if match:
        return int(float(match.group(1)) * 60)
    match = re.search(r"(\d+)\s*[- ]?\s*(minute|min|mins)\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_count(text: str, words: str) -> int | None:
    match = re.search(rf"(\d+)\s*(?:external\s+|extra\s+|visiting\s+)?(?:{words})\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_venue_code(text: str, known: set[str]) -> str | None:
    for match in VENUE_CODE.finditer(text):
        prefix, number = match.group(1).upper(), match.group(2)
        code = f"{prefix}-{number}"
        if code in known:
            return code
    return None


def extract_building(text: str, buildings: dict[int, str]) -> int | None:
    lowered = text.lower()
    for building_id, name in buildings.items():
        if name.lower() in lowered:
            return building_id
    simple = re.search(r"\b(?:academic\s+)?block\s+([abc])\b", lowered)
    if simple:
        target = f"academic block {simple.group(1)}"
        return next((i for i, n in buildings.items() if n.lower() == target), None)
    simple = re.search(r"lab complex\s*(\d)", lowered)
    if simple:
        return next((i for i, n in buildings.items() if n.lower() == f"lab complex {simple.group(1)}"), None)
    named = process.extractOne(lowered, {i: n.lower() for i, n in buildings.items()}, scorer=fuzz.partial_ratio, score_cutoff=92)
    return named[2] if named else None


def extract_sections(text: str) -> dict:
    params: dict = {}
    semester = re.search(r"sem(?:ester)?\s*-?\s*(\d)", text, re.IGNORECASE)
    if semester:
        params["semester"] = int(semester.group(1))
    dept = re.search(r"\b(" + "|".join(DEPTS) + r")\b", text, re.IGNORECASE)
    if dept:
        params["dept"] = dept.group(1).upper()
    names = re.search(r"\b(?:" + "|".join(DEPTS) + r")\s*-?\s*([ab])(?:\s*(?:and|&|,)\s*([ab]))?\b", text, re.IGNORECASE)
    if names:
        params["section_names"] = sorted({n.upper() for n in names.groups() if n})
    elif re.search(r"\ball\b.*\bsections?\b|\bsections?\b", text, re.IGNORECASE):
        params["section_names"] = ["A", "B"]
    return params


def venue_type_of(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"amphi|auditorium", lowered):
        return "amphitheatre"
    if "seminar" in lowered:
        return "seminar_hall"
    if re.search(r"\blabs?\b|laborator", lowered):
        return "lab"
    if re.search(r"class\s?room|\brooms?\b|lecture hall", lowered):
        return "classroom"
    return None


def ask(question: str, options: list[str], field_name: str) -> dict:
    return {"type": "clarify", "question": question, "options": options, "field": field_name}


def classify(text: str, has_date: bool, has_time: bool) -> str:
    lowered = text.lower()
    if re.search(r"\bghost\b", lowered):
        return "ghost"
    if re.search(r"utili[sz]ation|usage report|monthly report|how busy", lowered):
        return "utilisation"
    if re.search(r"\bclosed\b|\bclosure\b|under repair|shut down|\bout of service\b", lowered) and re.search(r"block|building|complex|lab|library|hall|venue", lowered):
        return "closure"
    if re.search(r"\brelease\b", lowered) and re.search(r"\bmy\b|\bclass\b|\bslot\b|\blecture\b", lowered):
        return "release"
    if re.search(r"booking\s*#?\s*\d+|show (me )?(my )?bookings?|my bookings", lowered):
        return "lookup"
    if re.search(r"common (free )?(slot|time)|slot for (sem|all)|extra (lecture|class)|quiz|common free", lowered) and re.search(r"sem|section|cse|ece|\bme\b|che|eee", lowered):
        return "cohort"
    resources = sum(bool(re.search(p, lowered)) for p in (r"guest|speaker|night|stay", r"\bcars?\b|parking|vehicles?|buses|bus\b", r"hall|amphi|auditorium|venue|room|workshop|conference|seminar"))
    if re.search(r"workshop|conference|symposium|fest\b|summit", lowered) and resources >= 2:
        return "bundle"
    if re.search(r"guest ?(house|room)|\bnights?\b|stay", lowered):
        return "guest_room"
    if re.search(r"parking|\bcars?\b|vehicles?|\bbus(es)?\b", lowered):
        return "parking"
    if re.search(r"\b(free|available|vacant|empty|open)\b", lowered) and (venue_type_of(text) or has_date or has_time):
        return "free_rooms"
    if re.search(r"\b(book|reserve|schedule|host|need|arrange)\b", lowered):
        return "book_venue"
    if (venue_type_of(text) or VENUE_CODE.search(text)) and (has_date or has_time):
        return "book_venue"
    if re.search(r"policy|policies|rule|allowed|lead time|how (many|long|much|early)|who approves|what happens|can (a|an|i|we|students?)|is (a|an|it)|are |does |what (is|are)|when (is|does|are)|which|why|who", lowered):
        return "policy"
    return "unknown"


def parse(message: str, now: datetime, venue_codes: set[str], buildings: dict[int, str]) -> Intent:
    text = word_to_number(message.strip())
    if is_injection(text):
        return Intent("injection", original=message)
    dates, remaining = extract_dates(text, now)
    start_min, end_min, remaining = extract_times(remaining)
    duration = extract_duration(remaining)
    kind = classify(text, bool(dates), start_min is not None)
    params: dict = {"dates": dates, "start_min": start_min, "end_min": end_min, "duration_min": duration, "venue_type": venue_type_of(text)}
    params["venue_code"] = extract_venue_code(text, venue_codes)
    if params["venue_code"] and not params["venue_type"]:
        prefix = params["venue_code"].split("-")[0]
        params["venue_type"] = {"L": "lab", "AMP": "amphitheatre", "SH": "seminar_hall"}.get(prefix, "classroom")
    attendees = re.search(r"(?:for|of|with|about|around|upto|up to)\s+(\d+)(?!\s*(?:night|hour|hr|min|car|vehicle|bus|day))", remaining, re.IGNORECASE) or re.search(r"(\d+)\s*(?:people|persons|students|attendees|participants|delegates|pax|seats)", remaining, re.IGNORECASE)
    params["attendees"] = int(attendee_group(attendees)) if attendees else None
    params["cars"] = extract_count(remaining, "cars?|vehicles?")
    params["bikes"] = extract_count(remaining, "bikes?|two[- ]wheelers?|motorcycles?")
    params["buses"] = extract_count(remaining, "buses|bus")
    params["nights"] = extract_count(remaining, "nights?")
    params["speakers"] = extract_count(remaining, "speakers?|guests?|visitors?|professors?")
    params["building_id"] = extract_building(text, buildings)
    params.update(extract_sections(text))
    params["recording"] = bool(re.search(r"record", text, re.IGNORECASE))
    title = re.search(r"(?:host|organi[sz]e|run|conduct)\s+an?\s+(?:\d+[- ]day\s+)?([A-Za-z0-9 ]+?)\s+(workshop|conference|symposium|fest|summit|seminar)", text, re.IGNORECASE)
    params["title"] = f"{title.group(1).strip()} {title.group(2).capitalize()}" if title else ""
    days = re.search(r"(\d+)[- ]day", text, re.IGNORECASE)
    params["event_days"] = int(days.group(1)) if days else None
    params["course_code"] = (re.search(r"\b([A-Z]{2,3}\d{3})\b", text) or [None, None])[1]
    params["booking_id"] = int(m.group(1)) if (m := re.search(r"booking\s*#?\s*(\d+)", text, re.IGNORECASE)) else None
    params["question"] = message
    return Intent(kind, params, original=message)


def attendee_group(match: re.Match) -> str:
    return next(g for g in match.groups() if g)
