import io

import pdfplumber
from openpyxl import load_workbook
from sqlmodel import select

from app.agent import narrative
from app.models import tables as t
from tests.conftest import login


def pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as document:
        return "\n".join(page.extract_text() or "" for page in document.pages)


def test_excel_exports_reopen_with_rows(client, session) -> None:
    admin = login(client, "admin")
    for name, expected in (("bookings", "Race"), ("guesthouse", "Room"), ("parking", "Lot"), ("audit", "Action")):
        response = client.get(f"/exports/{name}.xlsx", headers=admin)
        assert response.status_code == 200
        sheet = load_workbook(io.BytesIO(response.content)).active
        assert sheet.max_row >= 2 and sheet.max_column >= 4
    bookings = load_workbook(io.BytesIO(client.get("/exports/bookings.xlsx", headers=admin).content)).active
    assert bookings.max_row - 1 == len(session.exec(select(t.Booking)).all())
    assert client.get("/exports/bookings.xlsx", headers=login(client, "faculty01")).status_code == 403


def test_pdfs_contain_expected_content_and_qr_verifies(client, session) -> None:
    admin = login(client, "admin")
    confirmed = session.exec(select(t.Booking).where(t.Booking.status == "CONFIRMED", t.Booking.resource_type == "venue")).first()
    document = client.get(f"/exports/bookings/{confirmed.id}.pdf", headers=admin)
    assert document.status_code == 200 and "Booking confirmation" in pdf_text(document.content) and confirmed.event_title in pdf_text(document.content)
    token = client.get("/passes", params={"booking_id": confirmed.id}, headers=admin).json()[0]["token"]
    assert f"/pass/{token}" in pdf_text(document.content).replace("\n", "")
    client.post("/demo/now", json={"now": confirmed.start_dt.isoformat()}, headers=admin)
    assert client.get(f"/verify/pass/{token}").json()["result"] == "VALID"
    schedule = client.get("/exports/venue/1.pdf", params={"date_from": "2026-11-16", "days": 3}, headers=admin)
    assert "Schedule for A-101" in pdf_text(schedule.content)
    sheet = client.get("/exports/guesthouse/checkin.pdf", params={"day": "2026-11-19"}, headers=admin)
    assert "check-in sheet" in pdf_text(sheet.content).lower()


def test_monthly_report_exports_and_narrative_numbers_are_verified(client) -> None:
    admin = login(client, "admin")
    body = client.get("/reports/narrative", headers=admin).json()
    assert body["verified"] is True and narrative.numbers_verified(body["text"], body["kpis"])
    pdf = client.get("/reports/monthly.pdf", headers=admin)
    assert "Monthly utilisation report" in pdf_text(pdf.content)
    workbook = load_workbook(io.BytesIO(client.get("/reports/monthly.xlsx", headers=admin).content))
    assert {"Summary", "By type", "By building", "By hour"} <= set(workbook.sheetnames)


def test_narrative_check_rejects_invented_numbers() -> None:
    kpis = {"a": 42.5, "b": 7}
    assert narrative.numbers_verified("Utilisation was 42.5% and 7 rooms", kpis)
    assert narrative.numbers_verified("About 43% over 7 rooms", kpis)
    assert not narrative.numbers_verified("Utilisation hit 61% over 7 rooms", kpis)


def test_ics_feeds_are_valid_and_token_protected(client, session) -> None:
    faculty = login(client, "faculty01")
    venue_feed = client.get("/ics/venues/AMP-2.ics")
    assert venue_feed.text.startswith("BEGIN:VCALENDAR") and venue_feed.text.count("BEGIN:VEVENT") == venue_feed.text.count("END:VEVENT") >= 1
    assert "SUMMARY:Busy" in venue_feed.text
    token = client.get("/ics/token", headers=faculty).json()
    mine = client.get(token["url"])
    assert mine.status_code == 200 and mine.text.strip().endswith("END:VCALENDAR")
    assert client.get(f"/ics/users/{token['user_id']}.ics", params={"token": "wrong"}).status_code == 403
