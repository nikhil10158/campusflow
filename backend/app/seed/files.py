import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from app.config import DATA_DIR
from app.rules import load_rules
from app.seed.campus import hhmm_to_min
from app.seed.load import load_rows

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
GRID_HEADER = ["Day", "09:00-09:55", "10:00-10:55", "11:00-11:55", "12:00-12:55", "LUNCH", "14:00-14:55", "15:00-15:55", "16:00-16:55"]
PERIOD_COLUMNS = [1, 2, 3, 4, 6, 7, 8]
SAMPLE_SECTION = ("CSE", 5, "A")
SAMPLE_DIR = DATA_DIR / "timetables"


def sample_data() -> tuple[dict, list[dict], dict[int, dict], dict[int, str], dict[int, str]]:
    rows = load_rows()
    section = next(s for s in rows["section"] if (s["dept"], s["semester"], s["name"]) == SAMPLE_SECTION)
    entries = [e for e in rows["timetableentry"] if e["section_id"] == section["id"]]
    faculty = {f["id"]: f["name"] for f in rows["faculty"]}
    venues = {v["id"]: v["code"] for v in rows["venue"]}
    courses = {c["code"]: c for c in rows["course"]}
    return section, entries, courses, faculty, venues


def section_title(section: dict) -> str:
    return f"{section['dept']} Sem {section['semester']} - Section {section['name']}"


def period_span(entry: dict) -> tuple[int, int]:
    periods = load_rules().periods
    first = next(i for i, (a, _) in enumerate(periods) if hhmm_to_min(a) == entry["start_min"])
    last = next(i for i, (_, b) in enumerate(periods) if hhmm_to_min(b) == entry["end_min"])
    return first, last


def cell_text(entry: dict, faculty: dict[int, str], venues: dict[int, str]) -> str:
    code = entry["course_code"] + (" (T)" if entry["kind"] == "tutorial" else "")
    return f"{code} | {faculty[entry['faculty_id']]} | {venues[entry['venue_id']]}"


def write_flat_csv(path: Path, section: dict, entries: list[dict], faculty: dict, venues: dict) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Section", "Day", "Start", "End", "Course Code", "Course Name", "Faculty", "Room", "Type"])
        for entry in entries:
            writer.writerow([section_title(section), DAY_NAMES[entry["weekday"]], f"{entry['start_min'] // 60:02d}:{entry['start_min'] % 60:02d}", f"{entry['end_min'] // 60:02d}:{entry['end_min'] % 60:02d}", entry["course_code"], entry["course_name"], faculty[entry["faculty_id"]], venues[entry["venue_id"]], entry["kind"]])


def grid_rows(entries: list[dict], faculty: dict, venues: dict) -> tuple[list[list[str]], list[tuple[int, int, int]]]:
    table = [list(GRID_HEADER)] + [[name] + [""] * 8 for name in DAY_NAMES]
    spans: list[tuple[int, int, int]] = []
    for row in table[1:]:
        row[5] = "LUNCH"
    for entry in entries:
        first, last = period_span(entry)
        row = entry["weekday"] + 1
        table[row][PERIOD_COLUMNS[first]] = cell_text(entry, faculty, venues)
        if last > first:
            spans.append((row, PERIOD_COLUMNS[first], PERIOD_COLUMNS[last]))
    return table, spans


def write_grid_xlsx(path: Path, section: dict, entries: list[dict], faculty: dict, venues: dict) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f"{section['dept']}-{section['semester']}{section['name']}"
    sheet["A1"] = section_title(section)
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.merge_cells("A1:I1")
    sheet["A2"] = "SYNTHETIC - JKLU-like demo timetable. (T) marks a tutorial."
    sheet.merge_cells("A2:I2")
    table, spans = grid_rows(entries, faculty, venues)
    for number, row in enumerate(table, start=3):
        for column, value in enumerate(row, start=1):
            cell = sheet.cell(row=number, column=column, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
            if number == 3:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="DDE6F3")
    for row, first, last in spans:
        sheet.merge_cells(start_row=row + 3, start_column=first + 1, end_row=row + 3, end_column=last + 1)
    for column in range(1, 10):
        sheet.column_dimensions[chr(64 + column)].width = 26 if column > 1 else 8
    workbook.save(path)


def write_grid_pdf(path: Path, section: dict, entries: list[dict], faculty: dict, venues: dict) -> None:
    table, spans = grid_rows(entries, faculty, venues)
    styles = getSampleStyleSheet()
    wrapped = [
        [cell if row_number == 0 or column == 0 or cell in ("", "LUNCH") else Paragraph(cell.replace("&", "&amp;").replace(" | ", "<br/>"), styles["BodyText"]) for column, cell in enumerate(row)]
        for row_number, row in enumerate(table)
    ]
    commands = [("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONTSIZE", (0, 0), (-1, -1), 7)]
    for row, first, last in spans:
        commands.append(("SPAN", (first, row), (last, row)))
    sheet = Table(wrapped, colWidths=[40] + [88] * 8, rowHeights=[22] + [48] * 6)
    sheet.setStyle(TableStyle(commands))
    document = SimpleDocTemplate(str(path), pagesize=landscape(A4), title="Synthetic timetable")
    document.build([Paragraph(section_title(section), styles["Title"]), Paragraph("SYNTHETIC - JKLU-like demo timetable. (T) marks a tutorial.", styles["Normal"]), sheet])


def write_planted_errors(path: Path, section: dict, entries: list[dict], rows: dict) -> None:
    faculty = {f["id"]: f["name"] for f in rows["faculty"]}
    venues = {v["id"]: v["code"] for v in rows["venue"]}
    sibling = next(s for s in rows["section"] if (s["dept"], s["semester"], s["name"]) == (section["dept"], section["semester"], "B"))
    lectures = [e for e in entries if e["kind"] == "lecture"]
    first, second, third = lectures[0], lectures[1], lectures[2]

    def line(owner: dict, entry: dict, room: str, faculty_name: str, start: int | None = None, end: int | None = None, code: str | None = None) -> list:
        start_min = entry["start_min"] if start is None else start
        end_min = entry["end_min"] if end is None else end
        return [section_title(owner), DAY_NAMES[entry["weekday"]], f"{start_min // 60:02d}:{start_min % 60:02d}", f"{end_min // 60:02d}:{end_min % 60:02d}", code or entry["course_code"], entry["course_name"], faculty_name, room, entry["kind"]]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Section", "Day", "Start", "End", "Course Code", "Course Name", "Faculty", "Room", "Type"])
        writer.writerow(line(section, first, venues[first["venue_id"]], faculty[first["faculty_id"]]))
        writer.writerow(line(sibling, first, venues[first["venue_id"]], faculty[second["faculty_id"]], code="CS599"))
        writer.writerow(line(sibling, second, "A-101" if venues[second["venue_id"]] != "A-101" else "A-102", faculty[second["faculty_id"]]))
        writer.writerow(line(section, second, venues[second["venue_id"]], faculty[second["faculty_id"]]))
        writer.writerow(line(section, third, "X-999", faculty[third["faculty_id"]]))
        writer.writerow(line(section, third, venues[third["venue_id"]], faculty[third["faculty_id"]], start=third["start_min"] + 30, end=third["end_min"] + 30, code="CS598"))
        writer.writerow(line(section, third, venues[third["venue_id"]], faculty[third["faculty_id"]]))


def write_ambiguous(path: Path, section: dict, entries: list[dict], faculty: dict, venues: dict) -> None:
    entry = entries[0]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Section", "Day", "Start", "End", "Code", "Teacher", "Place"])
        writer.writerow([section_title(section), DAY_NAMES[entry["weekday"]], f"{entry['start_min'] // 60:02d}:{entry['start_min'] % 60:02d}", f"{entry['end_min'] // 60:02d}:{entry['end_min'] % 60:02d}", entry["course_code"], faculty[entry["faculty_id"]], "A 10"])


def generate_samples() -> list[Path]:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    section, entries, _, faculty, venues = sample_data()
    paths = {
        "cse5a_flat.csv": lambda p: write_flat_csv(p, section, entries, faculty, venues),
        "cse5a_grid.xlsx": lambda p: write_grid_xlsx(p, section, entries, faculty, venues),
        "cse5a_grid.pdf": lambda p: write_grid_pdf(p, section, entries, faculty, venues),
        "planted_errors.csv": lambda p: write_planted_errors(p, section, entries, rows),
        "ambiguous_headers.csv": lambda p: write_ambiguous(p, section, entries, faculty, venues),
    }
    written = []
    for name, writer in paths.items():
        target = SAMPLE_DIR / name
        writer(target)
        written.append(target)
    return written


if __name__ == "__main__":
    for path in generate_samples():
        print(path)
