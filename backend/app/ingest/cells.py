import re

TIME_RANGE = re.compile(r"(\d{1,2}[:.]\d{2})\s*(?:-|–|—|to)\s*(\d{1,2}[:.]\d{2})")
SECTION_TITLE = re.compile(r"(?P<dept>[A-Za-z]{2,5})\W*(?:sem(?:ester)?\W*)?(?P<sem>\d)\W*(?:section\W*)?(?P<name>[A-Za-z])\s*$", re.IGNORECASE)
CODE_PATTERN = re.compile(r"^[A-Z]{2,3}\d[\dA-Z]{1,3}$")
TUTORIAL_MARK = re.compile(r"\(\s*T\s*\)", re.IGNORECASE)


def split_cell(text: str) -> tuple[str, str, str, str]:
    cleaned = text.replace("\r", "")
    parts = [p.strip() for p in re.split(r"\||\n", cleaned) if p.strip()]
    if len(parts) == 1 and " - " in parts[0]:
        parts = [p.strip() for p in parts[0].split(" - ") if p.strip()]
    if not parts:
        return "", "", "", ""
    code_part = parts[0]
    kind = "tutorial" if TUTORIAL_MARK.search(code_part) else ""
    code = TUTORIAL_MARK.sub("", code_part).strip()
    faculty = parts[1] if len(parts) > 2 else ""
    room = parts[-1] if len(parts) > 1 else ""
    return code, faculty, room, kind


def is_time_range(text: str) -> bool:
    return bool(TIME_RANGE.search(str(text or "")))


def parse_time_range(text: str) -> tuple[str, str]:
    match = TIME_RANGE.search(text)
    assert match is not None
    return match.group(1).replace(".", ":"), match.group(2).replace(".", ":")


def find_section_title(texts: list[str]) -> str:
    for text in texts:
        candidate = str(text or "").strip()
        if candidate and SECTION_TITLE.search(candidate) and not is_time_range(candidate):
            return candidate
    return ""
