from sqlmodel import select

from app.ingest import normalise
from app.ingest.csv import parse_csv
from app.ingest.grid_xlsx import parse_grid_xlsx
from app.ingest.pdf import parse_pdf
from app.models import tables as t
from app.rules import load_rules
from app.seed.files import SAMPLE_DIR, SAMPLE_SECTION, generate_samples
from app.services import snapshot as snapshot_service
from tests.conftest import fresh, login


def sample(name: str) -> bytes:
    path = SAMPLE_DIR / name
    if not path.exists():
        generate_samples()
    return path.read_bytes()


def truth(session) -> set[tuple]:
    section = session.exec(select(t.Section).where(t.Section.dept == SAMPLE_SECTION[0], t.Section.semester == SAMPLE_SECTION[1], t.Section.name == SAMPLE_SECTION[2])).first()
    active = session.exec(select(t.TimetableVersion).where(t.TimetableVersion.status == "ACTIVE")).first()
    rows = session.exec(select(t.TimetableEntry).where(t.TimetableEntry.section_id == section.id, t.TimetableEntry.version_id == active.id)).all()
    return {(r.section_id, r.weekday, r.start_min, r.end_min, r.course_code, r.faculty_id, r.venue_id, r.kind) for r in rows}


def parsed_keys(session, parsed) -> set[tuple]:
    reference = normalise.build_reference(session)
    result = normalise.normalise_rows(parsed.rows, reference)
    assert not result.clarifications
    return {e.key() for e in result.entries}


def test_three_formats_normalise_to_the_same_entries(session) -> None:
    expected = truth(session)
    assert len(expected) >= 18
    assert parsed_keys(session, parse_csv(sample("cse5a_flat.csv"))) == expected
    assert parsed_keys(session, parse_grid_xlsx(sample("cse5a_grid.xlsx"))) == expected
    assert parsed_keys(session, parse_pdf(sample("cse5a_grid.pdf"))) == expected


def test_planted_error_file_reports_all_four_anomaly_types(client, session) -> None:
    admin = login(client, "admin")
    response = client.post("/timetables/upload", files={"file": ("planted_errors.csv", sample("planted_errors.csv"), "text/csv")}, headers=admin)
    assert response.status_code == 200, response.text
    body = response.json()
    codes = {issue["code"] for issue in body["issues"]}
    assert {"ROOM_DOUBLE_BOOKED", "FACULTY_CONFLICT", "UNKNOWN_ROOM", "SECTION_OVERLAP"} <= codes
    assert body["ready_to_import"] is False
    blocked = client.post(f"/timetables/{body['job_id']}/import", headers=admin)
    assert blocked.status_code == 409


def test_ambiguous_header_and_room_trigger_clarifications_then_import_and_rollback(client, session) -> None:
    admin = login(client, "admin")
    body = client.post("/timetables/upload", files={"file": ("ambiguous_headers.csv", sample("ambiguous_headers.csv"), "text/csv")}, headers=admin).json()
    assert body["clarifications"] and body["clarifications"][0]["id"] == "header:room"
    second = client.post(f"/timetables/{body['job_id']}/answer", json={"answers": {"header:room": "Place"}}, headers=admin).json()
    assert any(c["id"].startswith("room:") for c in second["clarifications"])
    question = next(c for c in second["clarifications"] if c["id"].startswith("room:"))
    third = client.post(f"/timetables/{body['job_id']}/answer", json={"answers": {question["id"]: question["options"][0]}}, headers=admin).json()
    assert not third["clarifications"]


def test_import_needs_admin_creates_new_version_and_can_roll_back(client, session) -> None:
    admin = login(client, "admin")
    faculty = login(client, "faculty01")
    assert client.post("/timetables/upload", files={"file": ("x.csv", sample("cse5a_flat.csv"), "text/csv")}, headers=faculty).status_code == 403
    body = client.post("/timetables/upload", files={"file": ("cse5a_flat.csv", sample("cse5a_flat.csv"), "text/csv")}, headers=admin).json()
    assert body["ready_to_import"] is True, body["issues"]
    assert body["diff"]["unchanged"] >= 18 and not body["diff"]["added"] and not body["diff"]["removed"]
    assert client.post(f"/timetables/{body['job_id']}/import", headers=faculty).status_code == 403
    done = client.post(f"/timetables/{body['job_id']}/import", headers=admin).json()
    assert done["status"] == "ACTIVE"
    versions = client.get("/timetables/versions", headers=admin).json()
    assert [v["status"] for v in versions].count("ACTIVE") == 1
    old = next(v for v in versions if v["status"] == "ARCHIVED")
    assert client.post(f"/timetables/versions/{old['id']}/rollback", headers=admin).json()["status"] == "ACTIVE"
    fresh(session)
    snapshot_service.reset_cache()
    assert len(snapshot_service.get_snapshot(session).entries) == len([e for e in session.exec(select(t.TimetableEntry).where(t.TimetableEntry.version_id == old["id"]))])
    log = client.get("/audit", params={"action": "timetable"}, headers=admin).json()["items"]
    assert {"timetable.imported", "timetable.rolled_back", "timetable.uploaded"} <= {i["action"] for i in log}
    assert client.get("/audit/verify", headers=admin).json()["ok"] is True
