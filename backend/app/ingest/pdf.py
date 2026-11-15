import io

import pdfplumber

from app.ingest.cells import find_section_title, is_time_range, parse_time_range, split_cell
from app.ingest.types import ParsedFile, RawRow


def clean(value) -> str | None:
    return None if value is None else str(value).strip()


def parse_table(table: list[list], title: str, page_number: int, parsed: ParsedFile) -> None:
    rows = [[clean(cell) for cell in row] for row in table]
    header_index = next((i for i, row in enumerate(rows) if sum(1 for c in row if c and is_time_range(c)) >= 3), -1)
    if header_index < 0:
        return
    columns = {column: parse_time_range(value) for column, value in enumerate(rows[header_index]) if value and is_time_range(value)}
    for row_number in range(header_index + 1, len(rows)):
        row = rows[row_number]
        day = (row[0] or "").strip()
        if not day:
            continue
        column = 1
        while column < len(row):
            value = row[column]
            if not value or column not in columns:
                column += 1
                continue
            last = column
            while last + 1 < len(row) and row[last + 1] is None and (last + 1) in columns:
                last += 1
            code, faculty, room, kind = split_cell(value)
            if code:
                parsed.rows.append(RawRow(section=title, day=day, start=columns[column][0], end=columns[last][1], code=code, faculty=faculty, room=room, kind=kind, source=f"page {page_number} row {row_number + 1}"))
            column = last + 1


def parse_pdf(content: bytes) -> ParsedFile:
    parsed = ParsedFile("grid_pdf")
    with pdfplumber.open(io.BytesIO(content)) as document:
        for number, page in enumerate(document.pages, start=1):
            title = find_section_title((page.extract_text() or "").splitlines())
            for table in page.extract_tables():
                parse_table(table, title, number, parsed)
    return parsed
