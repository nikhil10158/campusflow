from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from app.engine import validator
from app.models import tables as t
from app.rules import load_rules
from app.services import audit, race
from app.services import snapshot as snapshot_service
from tests.conftest import fresh, login

NOW = datetime(2026, 11, 16, 10, 0)


def window(days: int, start_hour: int, hours: int = 1) -> tuple[str, str]:
    start = (NOW + timedelta(days=days)).replace(hour=start_hour, minute=0)
    return start.isoformat(), (start + timedelta(hours=hours)).isoformat()


def free_classroom(client, headers, days: int = 3, hour: int = 11, attendees: int = 40) -> dict:
    start, end = window(days, hour)
    hits = client.get("/availability/search", params={"start": start, "end": end, "attendees": attendees, "types": "classroom"}, headers=headers).json()["hits"]
    assert hits
    return {"resource_type": "venue", "resource_id": hits[0]["venue_id"], "start": start, "end": end, "event_title": "Extra lecture", "attendees": attendees}


def assert_valid(session) -> None:
    fresh(session)
    snapshot = snapshot_service.load_snapshot(session, with_ghosts=False)
    assert validator.validate(snapshot, load_rules()) == []


def test_login_and_wrong_password(client) -> None:
    assert client.post("/auth/login", json={"email": "admin@jklu.demo", "password": "nope"}).status_code == 401
    headers = login(client, "faculty01")
    assert client.get("/auth/me", headers=headers).json()["role"] == "faculty"
    assert client.get("/venues").status_code == 401


def test_booking_cannot_confirm_without_every_approval_step(client, session) -> None:
    faculty = login(client, "faculty01")
    payload = free_classroom(client, faculty)
    held = client.post("/bookings", json=payload, headers=faculty)
    assert held.status_code == 200 and held.json()["status"] == "HELD"
    booking = session.get(t.Booking, held.json()["id"])
    assert booking.status == "HELD"
    assert_valid(session)
    admin = login(client, "admin")
    inbox = client.get("/approvals", headers=admin).json()
    mine = next(i for i in inbox if i["booking"]["id"] == booking.id)
    assert mine["still_valid"] is True
    done = client.post(f"/approvals/{mine['step_id']}/approve", json={}, headers=admin)
    assert done.status_code == 200 and done.json()["outcome"] == "confirmed"
    fresh(session)
    assert session.get(t.Booking, booking.id).status == "CONFIRMED"
    assert_valid(session)


def test_lab_chain_needs_labincharge_then_hod(client, session) -> None:
    faculty = login(client, "faculty01")
    start, end = window(4, 14, 2)
    lab = next(v for v in client.get("/venues", params={"type": "lab"}, headers=faculty).json() if v["lab_type"] == "cs")
    free = client.get("/availability/search", params={"start": start, "end": end, "types": "lab", "dept": "CSE"}, headers=faculty).json()["hits"]
    target = next(h for h in free if h["code"] in {lab["code"], h["code"]} and "cs" in h["name"].lower())
    held = client.post("/bookings", json={"resource_type": "venue", "resource_id": target["venue_id"], "start": start, "end": end, "event_title": "Lab practice", "attendees": 20}, headers=faculty)
    assert held.status_code == 200, held.text
    steps = held.json()["steps"]
    assert [s["scope"] for s in steps] == ["lab_incharge:cs", "hod:CSE"]
    hod = login(client, "hod.cse")
    assert client.post(f"/approvals/{steps[1]['id']}/approve", json={}, headers=hod).status_code == 409
    incharge = login(client, "labincharge.cse")
    assert client.post(f"/approvals/{steps[0]['id']}/approve", json={}, headers=incharge).status_code == 200
    fresh(session)
    assert session.get(t.Booking, held.json()["id"]).status == "HELD"
    assert client.post(f"/approvals/{steps[1]['id']}/approve", json={}, headers=hod).json()["outcome"] == "confirmed"


def test_wrong_scope_and_wrong_role_get_403(client, session) -> None:
    faculty = login(client, "faculty01")
    held = client.post("/bookings", json=free_classroom(client, faculty, days=5), headers=faculty).json()
    step_id = held["steps"][0]["id"]
    assert client.post(f"/approvals/{step_id}/approve", json={}, headers=login(client, "hod.cse")).status_code == 403
    assert client.post(f"/approvals/{step_id}/approve", json={}, headers=faculty).status_code == 403
    assert client.post(f"/approvals/{step_id}/approve", json={}, headers=login(client, "security01")).status_code == 403
    assert client.get("/audit", headers=faculty).status_code == 403
    assert client.post("/demo/now", json={"now": "2026-11-20T10:00:00"}, headers=faculty).status_code == 403


def test_rejection_needs_reason_and_frees_the_slot(client, session) -> None:
    faculty = login(client, "faculty01")
    payload = free_classroom(client, faculty, days=6)
    held = client.post("/bookings", json=payload, headers=faculty).json()
    admin = login(client, "admin")
    assert client.post(f"/approvals/{held['steps'][0]['id']}/reject", json={"comment": " "}, headers=admin).status_code == 422
    assert client.post(f"/approvals/{held['steps'][0]['id']}/reject", json={"comment": "Room needed for exam"}, headers=admin).status_code == 200
    again = client.post("/bookings", json=payload, headers=faculty)
    assert again.status_code == 200


def test_conflicting_request_returns_ranked_alternatives(client) -> None:
    faculty = login(client, "faculty01")
    payload = free_classroom(client, faculty, days=7)
    assert client.post("/bookings", json=payload, headers=faculty).status_code == 200
    clash = client.post("/bookings", json=payload, headers=login(client, "faculty02"))
    assert clash.status_code == 409
    body = clash.json()
    assert len(body["alternatives"]) >= 2
    assert body["alternatives"][0]["cost"] <= body["alternatives"][-1]["cost"]


def test_students_need_sponsor_and_see_only_their_bookings(client) -> None:
    student = login(client, "student01")
    payload = free_classroom(client, student, days=3, hour=15, attendees=30)
    assert client.post("/bookings", json=payload, headers=student).status_code == 409
    sponsor = next(u for u in client.get("/auth/demo-users").json() if u["email"] == "faculty01@jklu.demo")
    users = {u["email"]: u for u in client.get("/auth/demo-users").json()}
    assert sponsor
    listing = client.get("/bookings", headers=student).json()
    assert all(b["requester_id"] is not None for b in listing)
    other = client.get("/bookings/2", headers=student)
    assert other.status_code in (200, 403)
    faculty_listing = client.get("/bookings", headers=login(client, "faculty05")).json()
    assert any(b["event_title"] == "Busy" for b in faculty_listing)
    assert users


def test_calendars_show_busy_only_to_non_admins(client) -> None:
    faculty = login(client, "faculty01")
    venue = client.get("/venues", params={"type": "amphitheatre"}, headers=faculty).json()[1]
    timeline = client.get(f"/availability/venue/{venue['id']}", params={"date_from": "2026-11-20", "days": 1}, headers=faculty).json()
    labels = {s["label"] for d in timeline["days"] for s in d["segments"]}
    assert labels == {"Busy"}
    admin_view = client.get(f"/availability/venue/{venue['id']}", params={"date_from": "2026-11-20", "days": 1}, headers=login(client, "admin")).json()
    assert any("Founders" in s["label"] for d in admin_view["days"] for s in d["segments"])


def test_stale_approval_is_blocked_with_alternatives(client, session) -> None:
    faculty = login(client, "faculty01")
    held = client.post("/bookings", json=free_classroom(client, faculty, days=8), headers=faculty).json()
    fresh(session)
    booking = session.get(t.Booking, held["id"])
    session.add(t.Maintenance(resource_type="venue", resource_id=booking.resource_id, start_dt=booking.start_dt - timedelta(hours=1), end_dt=booking.end_dt + timedelta(hours=1), reason="Burst pipe"))
    session.commit()
    admin = login(client, "admin")
    stale = client.post(f"/approvals/{held['steps'][0]['id']}/approve", json={}, headers=admin)
    assert stale.status_code == 409 and "Stale" in stale.json()["detail"]
    assert stale.json()["alternatives"]
    item = next(i for i in client.get("/approvals", headers=admin).json() if i["booking"]["id"] == held["id"])
    assert item["still_valid"] is False


def test_hold_expiry_and_escalation_follow_the_demo_clock(client, session) -> None:
    admin = login(client, "admin")
    assert client.post("/demo/now", json={"now": "2026-11-16T22:00:00"}, headers=admin).json()["escalated"] > 0
    inbox = client.get("/approvals", headers=admin).json()
    assert any(i["escalated"] for i in inbox)
    result = client.post("/demo/now", json={"now": "2026-11-17T12:00:00"}, headers=admin).json()
    assert result["expired"] > 0
    fresh(session)
    assert session.exec(select(t.Booking).where(t.Booking.status == "EXPIRED")).first() is not None


def test_bundle_is_atomic_and_confirms_only_after_all_components_approve(client, session) -> None:
    faculty = login(client, "faculty01")
    venue = next(v for v in client.get("/venues", params={"type": "amphitheatre"}, headers=faculty).json() if v["code"] == "AMP-1")
    body = {
        "title": "AI Workshop", "external_speakers": 2,
        "components": [
            {"resource_type": "venue", "resource_id": venue["id"], "start": "2026-12-03T10:00:00", "end": "2026-12-03T17:00:00", "attendees": 80, "event_title": "Main hall"},
            {"resource_type": "guest_room", "resource_id": 4, "start": "2026-12-02T14:00:00", "end": "2026-12-04T11:00:00", "attendees": 2, "event_title": "Speaker rooms", "meta": {"guests": 2}},
            {"resource_type": "parking", "resource_id": 1, "start": "2026-12-03T09:00:00", "end": "2026-12-03T18:00:00", "attendees": 80, "qty": 12, "event_title": "Cars", "meta": {"vehicles": {"car": 12}}},
        ],
    }
    created = client.post("/bundles", json=body, headers=faculty)
    assert created.status_code == 200, created.text
    detail = created.json()
    assert detail["status"] == "SUBMITTED" and len(detail["components"]) == 3
    bad = {**body, "components": [body["components"][0], {**body["components"][1], "start": "2026-12-04T14:00:00", "end": "2026-12-05T11:00:00"}, body["components"][2]]}
    before = session.exec(select(t.Booking)).all()
    assert client.post("/bundles", json=bad, headers=faculty).status_code == 409
    fresh(session)
    assert len(session.exec(select(t.Booking)).all()) == len(before)
    admin = login(client, "admin")
    for approver in ("estate", "guesthouse.mgr", "parking.officer"):
        headers = login(client, approver)
        for item in client.get("/approvals", headers=headers).json():
            if item["booking"]["bundle_id"] == detail["id"]:
                outcome = client.post(f"/approvals/{item['step_id']}/approve", json={}, headers=headers).json()
    final = client.get(f"/bundles/{detail['id']}", headers=faculty).json()
    assert final["status"] == "CONFIRMED", final
    assert all(c["status"] == "CONFIRMED" for c in final["components"])
    fresh(session)
    assert_valid(session)
    assert client.get("/audit/verify", headers=admin).json()["ok"] is True
    assert outcome["outcome"] == "confirmed"


def test_bundle_rejection_leaves_partial_and_cancel_all_compensates(client, session) -> None:
    faculty = login(client, "faculty01")
    venue = next(v for v in client.get("/venues", params={"type": "amphitheatre"}, headers=faculty).json() if v["code"] == "AMP-1")
    body = {"title": "Seminar", "components": [
        {"resource_type": "venue", "resource_id": venue["id"], "start": "2026-12-08T10:00:00", "end": "2026-12-08T12:00:00", "attendees": 60, "event_title": "Hall"},
        {"resource_type": "parking", "resource_id": 1, "start": "2026-12-08T09:00:00", "end": "2026-12-08T13:00:00", "attendees": 60, "qty": 10, "event_title": "Cars", "meta": {"vehicles": {"car": 10}}},
    ]}
    detail = client.post("/bundles", json=body, headers=faculty).json()
    officer = login(client, "parking.officer")
    step = next(i for i in client.get("/approvals", headers=officer).json() if i["booking"]["bundle_id"] == detail["id"])
    assert client.post(f"/approvals/{step['step_id']}/reject", json={"comment": "Lot closed for paving"}, headers=officer).status_code == 200
    assert client.get(f"/bundles/{detail['id']}", headers=faculty).json()["status"] == "PARTIAL"
    cancelled = client.post(f"/bundles/{detail['id']}/cancel", headers=faculty).json()
    assert cancelled["status"] == "CANCELLED"
    final = client.get(f"/bundles/{detail['id']}", headers=faculty).json()
    assert all(c["status"] in ("CANCELLED", "REJECTED") for c in final["components"])


def test_race_has_exactly_one_winner_and_a_clean_validator(client, session) -> None:
    outcome = race.run_race(20)
    assert outcome["winners"] == 1
    assert outcome["winners"] + outcome["conflicts"] == 20
    assert outcome["validator_violations"] == []


def test_audit_chain_detects_tampering(client, session) -> None:
    admin = login(client, "admin")
    client.get("/auth/me", headers=admin)
    fresh(session)
    assert audit.verify(session)["ok"] is True
    from sqlalchemy import text

    with session.get_bind().begin() as connection:
        connection.execute(text("DROP TRIGGER auditlog_no_update"))
        connection.execute(text("UPDATE auditlog SET actor = 'mallory' WHERE id = 2"))
    fresh(session)
    verdict = audit.verify(session)
    assert verdict["ok"] is False and verdict["broken_at"] == 2


def test_audit_log_blocks_update_and_delete(session) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DatabaseError

    with pytest.raises(DatabaseError):
        session.execute(text("UPDATE auditlog SET actor = 'x'"))
    session.rollback()
    with pytest.raises(DatabaseError):
        session.execute(text("DELETE FROM auditlog"))


def test_pass_scan_results_and_no_show_release(client, session) -> None:
    admin = login(client, "admin")
    security = login(client, "security01")
    parking_booking = session.exec(select(t.Booking).where(t.Booking.resource_type == "parking", t.Booking.status == "CONFIRMED")).first()
    tokens = client.get("/passes", params={"booking_id": parking_booking.id}, headers=admin).json()
    token = tokens[0]["token"]
    client.post("/demo/now", json={"now": parking_booking.start_dt.isoformat()}, headers=admin)
    assert client.post("/passes/scan", json={"token": token, "lot_id": parking_booking.resource_id}, headers=security).json()["result"] == "VALID"
    assert client.post("/passes/scan", json={"token": token, "lot_id": 99}, headers=security).json()["result"] == "WRONG_LOT"
    assert client.get(f"/verify/pass/{token}x").json()["result"] == "NOT_FOUND"
    client.post("/demo/now", json={"now": (parking_booking.end_dt + timedelta(hours=1)).isoformat()}, headers=admin)
    assert client.post("/passes/scan", json={"token": token}, headers=security).json()["result"] == "EXPIRED"
    other = next(b for b in session.exec(select(t.Booking).where(t.Booking.resource_type == "parking", t.Booking.status == "CONFIRMED")) if b.id != parking_booking.id)
    client.post("/demo/now", json={"now": (other.start_dt + timedelta(minutes=45)).isoformat()}, headers=admin)
    proposals = client.get("/parking/no-shows", headers=security).json()
    assert any(p["booking_id"] == other.id for p in proposals)
    assert client.post(f"/parking/no-shows/{other.id}/release", headers=security).status_code == 200


def test_ghost_release_flips_slot_and_search_returns_it(client, session) -> None:
    admin = login(client, "admin")
    ghosts = client.get("/reports/ghosts", headers=admin).json()
    assert len(ghosts["ghosts"]) == 6 and ghosts["projected_uplift_hours_per_week"] > 0
    ghost = ghosts["ghosts"][0]
    proposal = client.post("/exceptions/propose-release", json={"entry_id": ghost["entry_id"], "date": ghost["next_date"], "reason": "Low attendance"}, headers=admin)
    assert proposal.status_code == 200
    day = ghost["next_date"]
    start = datetime.fromisoformat(f"{day}T00:00:00") + timedelta(minutes=ghost["start_min"])
    end = datetime.fromisoformat(f"{day}T00:00:00") + timedelta(minutes=ghost["end_min"])
    params = {"start": start.isoformat(), "end": end.isoformat(), "types": "classroom,seminar_hall"}
    before = client.get("/availability/search", params=params, headers=admin).json()
    assert ghost["venue_code"] not in {h["code"] for h in before["hits"]}
    dept = ghost['section'].split()[0].lower()
    other = 'hod.me' if dept != 'me' else 'hod.cse'
    assert client.post(f"/exceptions/{proposal.json()['id']}/approve", json={}, headers=login(client, other)).status_code == 403
    assert client.post(f"/exceptions/{proposal.json()['id']}/approve", json={}, headers=login(client, f'hod.{dept}')).status_code == 200
    after = client.get("/availability/search", params=params, headers=admin).json()
    released = next(h for h in after["hits"] if h["code"] == ghost["venue_code"])
    assert released["state"] == "FREE_RELEASED"




def test_race_endpoint_is_admin_only_and_reports_one_winner(client) -> None:
    assert client.post("/simulate/race", headers=login(client, "faculty01")).status_code == 403
    body = client.post("/simulate/race", params={"racers": 20}, headers=login(client, "admin")).json()
    assert body["winners"] == 1 and body["validator_violations"] == []

