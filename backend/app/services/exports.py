import io
from datetime import date, datetime, timedelta

import qrcode
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlmodel import Session, select

from app.config import get_settings
from app.models import tables as t
from app.services import passes

STYLES = getSampleStyleSheet()
BANNER = "SYNTHETIC DATA - JKLU-like demo campus"


def qr_image(text: str, size_mm: float = 38) -> Image:
    buffer = io.BytesIO()
    qrcode.make(text).save(buffer, format="PNG")
    buffer.seek(0)
    return Image(buffer, width=size_mm * mm, height=size_mm * mm)


def pass_url(token: str) -> str:
    return f"{get_settings().frontend_origins[0]}/pass/{token}"


def grid(rows: list[list], widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde6f3")), ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def build_pdf(title: str, story: list) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title=title, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    document.build([Paragraph(title, STYLES["Title"]), Paragraph(BANNER, STYLES["Italic"]), Spacer(1, 6 * mm), *story])
    return buffer.getvalue()


def stamp(moment: datetime) -> str:
    return moment.strftime("%d %b %Y %H:%M")


def venue_schedule_pdf(session: Session, venue_id: int, first: date, days: int, redact: bool) -> bytes:
    from app.services.snapshot import get_index

    index = get_index(session)
    venue = index.snapshot.venue(venue_id)
    rows = [["Date", "Time", "Layer", "What"]]
    for offset in range(days):
        day = first + timedelta(days=offset)
        if index.offset(day) is None:
            continue
        for segment in index.day_segments(venue_id, day):
            rows.append([f"{day:%a %d %b}", segment.time_text(), segment.layer, "Busy" if redact else segment.label])
    if len(rows) == 1:
        rows.append(["-", "-", "-", "Nothing scheduled"])
    return build_pdf(f"Schedule for {venue.code} ({venue.name})", [grid(rows, [30 * mm, 30 * mm, 28 * mm, 90 * mm])])


def booking_pdf(session: Session, booking: t.Booking) -> bytes:
    venue = session.get(t.Venue, booking.resource_id) if booking.resource_type == "venue" else None
    rows = [["Field", "Value"], ["Booking", f"#{booking.id}"], ["Status", booking.status], ["Title", booking.event_title], ["Resource", f"{booking.resource_type} {venue.code if venue else booking.resource_id}"], ["From", stamp(booking.start_dt)], ["To", stamp(booking.end_dt)], ["Attendees", str(booking.attendees)]]
    story: list = [grid(rows, [40 * mm, 120 * mm]), Spacer(1, 6 * mm)]
    issued = session.exec(select(t.Pass).where(t.Pass.booking_id == booking.id, t.Pass.revoked == False)).first()  # noqa: E712
    if booking.status == "CONFIRMED" and issued:
        token = passes.token_of(issued)
        story += [Paragraph("Scan to verify this booking", STYLES["Normal"]), qr_image(pass_url(token)), Paragraph(pass_url(token), STYLES["Code"])]
    return build_pdf("Booking confirmation", story)


def pass_pdf(session: Session, issued: t.Pass) -> bytes:
    token = passes.token_of(issued)
    rows = [["Field", "Value"], ["Type", issued.type], ["Plate", issued.plate or "-"], ["Valid from", stamp(issued.valid_from)], ["Valid to", stamp(issued.valid_to)], ["Resource", str(issued.resource_id)]]
    return build_pdf("Pass", [grid(rows, [40 * mm, 120 * mm]), Spacer(1, 6 * mm), qr_image(pass_url(token), 50), Paragraph(pass_url(token), STYLES["Code"])])


def checkin_sheet_pdf(session: Session, day: date) -> bytes:
    rooms = {r.id: r for r in session.exec(select(t.GuestRoom))}
    guests = {g.id: g for g in session.exec(select(t.Guest))}
    rows = [["Room", "Guest", "Category", "Check-in", "Check-out", "Signature"]]
    for booking in session.exec(select(t.Booking).where(t.Booking.resource_type == "guest_room", t.Booking.status == "CONFIRMED").order_by(t.Booking.start_dt)):
        if booking.start_dt.date() == day:
            for guest_id in booking.meta_json.get("guest_ids", [None]):
                guest = guests.get(guest_id)
                rows.append([rooms[booking.resource_id].code, guest.name if guest else booking.event_title, guest.category if guest else "-", stamp(booking.start_dt), stamp(booking.end_dt), ""])
    if len(rows) == 1:
        rows.append(["-", "No arrivals on this date", "", "", "", ""])
    return build_pdf(f"Guest check-in sheet for {day:%d %b %Y}", [grid(rows)])


def workbook_bytes(sheets: dict[str, list[list]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name[:31])
        for row in rows:
            sheet.append(row)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def bookings_rows(session: Session) -> list[list]:
    rows = [["ID", "Resource type", "Resource", "Title", "Start", "End", "Attendees", "Status", "Bundle"]]
    for b in session.exec(select(t.Booking).order_by(t.Booking.id)):
        rows.append([b.id, b.resource_type, b.resource_id, b.event_title, b.start_dt.isoformat(), b.end_dt.isoformat(), b.attendees, b.status, b.bundle_id])
    return rows


def guesthouse_rows(session: Session) -> list[list]:
    rooms = {r.id: r for r in session.exec(select(t.GuestRoom))}
    rows = [["Room", "Type", "Check-in", "Check-out", "Nights", "Tariff", "Status"]]
    for b in session.exec(select(t.Booking).where(t.Booking.resource_type == "guest_room").order_by(t.Booking.start_dt)):
        nights = (b.end_dt.date() - b.start_dt.date()).days
        rows.append([rooms[b.resource_id].code, rooms[b.resource_id].type, b.start_dt.isoformat(), b.end_dt.isoformat(), nights, nights * rooms[b.resource_id].tariff_per_night, b.status])
    return rows


def parking_rows(session: Session) -> list[list]:
    lots = {l.id: l.name for l in session.exec(select(t.ParkingLot))}
    rows = [["Lot", "Start", "End", "Vehicles", "Status", "Title"]]
    for b in session.exec(select(t.Booking).where(t.Booking.resource_type == "parking").order_by(t.Booking.start_dt)):
        rows.append([lots[b.resource_id], b.start_dt.isoformat(), b.end_dt.isoformat(), str(b.meta_json.get("vehicles", b.qty)), b.status, b.event_title])
    return rows


def audit_rows(session: Session) -> list[list]:
    rows = [["ID", "Time", "Actor", "Action", "Hash"]]
    for a in session.exec(select(t.AuditLog).order_by(t.AuditLog.id)):
        rows.append([a.id, a.ts.isoformat(), a.actor, a.action, a.hash])
    return rows


def report_rows(kpis: dict) -> dict[str, list[list]]:
    summary = [["Metric", "Value"]]
    for key in ("classroom_time_utilisation_pct", "timetable_utilisation_pct", "total_utilisation_pct", "seat_utilisation_pct", "peak_utilisation_pct", "off_peak_utilisation_pct", "ghost_classes", "ghost_bookable_hours_per_week"):
        summary.append([key, kpis[key]])
    for key, value in kpis["guest_house"].items():
        summary.append([f"guest_house.{key}", value])
    for key, value in kpis["parking"].items():
        summary.append([f"parking.{key}", value])
    return {"Summary": summary, "By type": [["Type", "Utilisation %"], *kpis["by_type"].items()], "By building": [["Building", "Utilisation %"], *kpis["by_building"].items()], "By hour": [["Hour", "Utilisation"], *[[h["hour"], h["utilisation"]] for h in kpis["hourly"]]]}


def monthly_pdf(kpis: dict, narrative: dict) -> bytes:
    summary = [["Metric", "Value"]] + report_rows(kpis)["Summary"][1:]
    story = [Paragraph(f"Period {kpis['period']['start']} to {kpis['period']['end']}", STYLES["Heading3"]), grid(summary, [100 * mm, 60 * mm]), Spacer(1, 6 * mm), Paragraph("Narrative", STYLES["Heading3"]), Paragraph(narrative["text"], STYLES["Normal"]), Paragraph(f"Numbers verified against computed KPIs: {'yes' if narrative['verified'] else 'no'} ({narrative['mode']})", STYLES["Italic"])]
    return build_pdf("Monthly utilisation report", story)
