import io

from openpyxl import load_workbook

from app.ingest.cells import find_section_title, is_time_range, parse_time_range, split_cell
from app.ingest.types import ParsedFile, RawRow

DAY_COLUMN_LABELS = ("day", "days")


def find_header(rows: list[list]) -> tuple[int, dict[int, tuple[str, str]]]:
    for number, row in enumerate(rows):
        columns = {column: parse_time_range(str(value)) for column, value in enumerate(row) if value and is_time_range(str(value))}
        if len(columns) >= 3:
            return number, columns
    return -1, {}


def parse_sheet(sheet, parsed: ParsedFile) -> None:
    rows = [[cell.value for cell in row] for row in sheet.iter_rows()]
    header_row, columns = find_header(rows)
    if header_row < 0:
        parsed.notes.append(f"Sheet {sheet.title}: no row of time ranges found")
        return
    title = find_section_title([str(v) for row in rows[:header_row] for v in row if v] + [sheet.title])
    merges = {(r.min_row - 1, r.min_col - 1): (r.max_col - 1) for r in sheet.merged_cells.ranges}
    for row_number in range(header_row + 1, len(rows)):
        day = str(rows[row_number][0] or "").strip()
        if not day:
            continue
        for column, value in enumerate(rows[row_number]):
            if column == 0 or value in (None, "") or column not in columns:
                continue
            last = merges.get((row_number, column), column)
            last_column = max((c for c in columns if column <= c <= last), default=column)
            code, faculty, room, kind = split_cell(str(value))
            if not code:
                continue
            parsed.rows.append(RawRow(section=title, day=day, start=columns[column][0], end=columns[last_column][1], code=code, faculty=faculty, room=room, kind=kind, source=f"{sheet.title}!R{row_number + 1}C{column + 1}"))


def parse_grid_xlsx(content: bytes) -> ParsedFile:
    parsed = ParsedFile("grid_xlsx")
    workbook = load_workbook(io.BytesIO(content), data_only=True)
    for sheet in workbook.worksheets:
        parse_sheet(sheet, parsed)
    return parsed
