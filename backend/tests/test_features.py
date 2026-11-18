from datetime import datetime, timedelta
from email.message import EmailMessage

from sqlmodel import select

from app.models import tables as t
from app.services import mailer
from tests.conftest import fresh, login
from tests.test_workflow import free_classroom


def submit(client, headers, **kwargs) -> dict:
    payload = free_classroom(client, headers, **kwargs)
    response = client.post("/bookings", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def inbox_entry(client, admin, booking_id: int) -> dict:
    return next(item for item in client.get("/approvals", headers=admin).json() if item["booking"]["id"] == booking_id)


def test_notifications_are_stored_per_user_and_can_be_read(client, session) -> None:
    faculty = login(client, "faculty01")
    admin = login(client, "admin")
    booking = submit(client, faculty)
    admin_feed = client.get("/notifications", headers=admin).json()
    assert admin_feed["unread"] >= 1
    assert any(item["kind"] == "new_request" and item["booking_id"] == booking["id"] for item in admin_feed["items"])
    own_feed = client.get("/notifications", headers=faculty).json()
    assert any("submitted" in item["title"] for item in own_feed["items"])
    assert all(item["kind"] != "new_request" for item in own_feed["items"])
    first = admin_feed["items"][0]
    assert client.post(f"/notifications/{first['id']}/read", headers=faculty).status_code == 404
    after = client.post(f"/notifications/{first['id']}/read", headers=admin).json()
    assert after["unread"] == admin_feed["unread"] - 1
    assert client.post("/notifications/read-all", headers=admin).json() == {"unread": 0}
    again = client.get("/notifications", headers=admin).json()
    assert again["unread"] == 0 and len(again["items"]) == len(admin_feed["items"])
    assert client.get("/notifications").status_code == 401


def test_requester_is_notified_when_approved_or_rejected(client, session) -> None:
    faculty = login(client, "faculty01")
    admin = login(client, "admin")
    approved = submit(client, faculty, days=3, hour=11)
    entry = inbox_entry(client, admin, approved["id"])
    client.post(f"/approvals/{entry['step_id']}/approve", json={}, headers=admin)
    rejected = submit(client, faculty, days=4, hour=11)
    entry = inbox_entry(client, admin, rejected["id"])
    client.post(f"/approvals/{entry['step_id']}/reject", json={"comment": "Room reserved for exams"}, headers=admin)
    titles = [item["title"] for item in client.get("/notifications", headers=faculty).json()["items"]]
    assert f"Booking #{approved['id']} confirmed" in titles
    assert f"Booking #{rejected['id']} rejected" in titles


def test_status_tracker_moves_from_pending_to_approved_or_rejected(client, session) -> None:
    faculty = login(client, "faculty01")
    admin = login(client, "admin")
    booking = submit(client, faculty)
    assert client.get(f"/bookings/{booking['id']}", headers=faculty).json()["track"]["status"] == "PENDING"
    entry = inbox_entry(client, admin, booking["id"])
    client.post(f"/approvals/{entry['step_id']}/approve", json={}, headers=admin)
    assert client.get(f"/bookings/{booking['id']}", headers=faculty).json()["track"]["label"] == "Approved"
    lab = free_lab_booking(client, faculty)
    assert client.get(f"/bookings/{lab['id']}", headers=faculty).json()["track"]["status"] == "PENDING"
    labincharge = login(client, "labincharge.cse")
    step = inbox_entry(client, labincharge, lab["id"])
    client.post(f"/approvals/{step['step_id']}/approve", json={}, headers=labincharge)
    assert client.get(f"/bookings/{lab['id']}", headers=faculty).json()["track"]["label"] == "Under Review"
    hod = login(client, "hod.cse")
    step = inbox_entry(client, hod, lab["id"])
    client.post(f"/approvals/{step['step_id']}/reject", json={"comment": "Lab under audit"}, headers=hod)
    assert client.get(f"/bookings/{lab['id']}", headers=faculty).json()["track"]["label"] == "Rejected"


def free_lab_booking(client, headers) -> dict:
    start = (datetime(2026, 11, 16, 10, 0) + timedelta(days=4)).replace(hour=14).isoformat()
    end = (datetime(2026, 11, 16, 10, 0) + timedelta(days=4)).replace(hour=16).isoformat()
    free = client.get("/availability/search", params={"start": start, "end": end, "types": "lab", "dept": "CSE"}, headers=headers).json()["hits"]
    target = next(hit for hit in free if "cs" in hit["name"].lower())
    response = client.post("/bookings", json={"resource_type": "venue", "resource_id": target["venue_id"], "start": start, "end": end, "event_title": "Lab practice", "attendees": 20}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_double_booking_is_blocked_with_alternatives(client, session) -> None:
    faculty = login(client, "faculty01")
    payload = free_classroom(client, faculty, days=6, hour=15)
    assert client.post("/bookings", json=payload, headers=faculty).status_code == 200
    second = client.post("/bookings", json={**payload, "event_title": "Clash"}, headers=login(client, "faculty02"))
    assert second.status_code == 409
    assert second.json()["alternatives"]


def test_rejection_recovery_shows_reason_and_resubmits_without_retyping(client, session) -> None:
    faculty = login(client, "faculty01")
    admin = login(client, "admin")
    original = submit(client, faculty, days=3, hour=11, attendees=50)
    entry = inbox_entry(client, admin, original["id"])
    client.post(f"/approvals/{entry['step_id']}/reject", json={"comment": "Needed for an exam"}, headers=admin)
    view = client.get(f"/bookings/{original['id']}/recovery", headers=faculty).json()
    assert view["rejection"]["reason"] == "Needed for an exam"
    assert view["rejection"]["by"]
    assert view["original"]["attendees"] == 50 and view["original"]["event_title"] == "Extra lecture"
    assert view["alternatives"]
    choice = view["alternatives"][0]["parts"][0]
    assert choice["resource_id"] != original["resource_id"] or choice["start"] != original["start"]
    assert all(option["same_type"] for option in view["alternatives"] if option["same_time"])
    assert client.get(f"/bookings/{original['id']}/recovery", headers=login(client, "faculty02")).status_code == 403
    resubmitted = client.post(f"/bookings/{original['id']}/resubmit", json={"resource_id": choice["resource_id"], "start": choice["start"], "end": choice["end"]}, headers=faculty)
    assert resubmitted.status_code == 200, resubmitted.text
    body = resubmitted.json()
    assert body["status"] == "HELD" and body["event_title"] == "Extra lecture" and body["attendees"] == 50
    assert body["meta"]["resubmitted_from"] == original["id"]
    assert client.post(f"/bookings/{original['id']}/resubmit", json={}, headers=faculty).status_code == 409
    assert client.get(f"/bookings/{original['id']}/recovery", headers=faculty).json()["resubmitted_as"] == body["id"]
    pending = inbox_entry(client, admin, body["id"])
    assert pending["step_id"]
    assert client.get(f"/bookings/{body['id']}/recovery", headers=faculty).status_code == 409


def test_resubmitting_someone_elses_request_is_refused(client, session) -> None:
    faculty = login(client, "faculty01")
    admin = login(client, "admin")
    original = submit(client, faculty)
    entry = inbox_entry(client, admin, original["id"])
    client.post(f"/approvals/{entry['step_id']}/reject", json={"comment": "No"}, headers=admin)
    assert client.post(f"/bookings/{original['id']}/resubmit", json={}, headers=login(client, "faculty02")).status_code == 403
    assert client.post(f"/bookings/{original['id']}/resubmit", json={}, headers=admin).status_code == 403


def test_pass_is_valid_only_while_booking_is_confirmed(client, session) -> None:
    faculty = login(client, "faculty01")
    admin = login(client, "admin")
    booking = submit(client, faculty, days=2, hour=15)
    assert client.get("/passes", params={"booking_id": booking["id"]}, headers=faculty).json() == []
    entry = inbox_entry(client, admin, booking["id"])
    client.post(f"/approvals/{entry['step_id']}/approve", json={}, headers=admin)
    issued = client.get("/passes", params={"booking_id": booking["id"]}, headers=faculty).json()
    assert len(issued) == 1
    token = issued[0]["token"]
    scan = client.post("/passes/scan", json={"token": token}, headers=login(client, "security01")).json()
    assert scan["pass"]["booking"]["title"] == "Extra lecture"
    client.post(f"/bookings/{booking['id']}/cancel", headers=faculty)
    assert client.get(f"/verify/pass/{token}").json()["result"] == "REVOKED"
    assert client.post("/passes/scan", json={"token": token}, headers=faculty).status_code == 403


def test_pass_check_rejects_a_pass_whose_booking_is_no_longer_confirmed(client, session) -> None:
    faculty = login(client, "faculty01")
    admin = login(client, "admin")
    booking = submit(client, faculty, days=2, hour=15)
    entry = inbox_entry(client, admin, booking["id"])
    client.post(f"/approvals/{entry['step_id']}/approve", json={}, headers=admin)
    token = client.get("/passes", params={"booking_id": booking["id"]}, headers=faculty).json()[0]["token"]
    row = session.get(t.Booking, booking["id"])
    row.status = "REJECTED"
    session.add(row)
    session.commit()
    assert client.get(f"/verify/pass/{token}").json()["result"] == "REVOKED"
    assert client.get("/verify/pass/12.notarealtoken").json()["result"] == "NOT_FOUND"


def test_approval_trail_lists_who_did_what_and_is_access_controlled(client, session) -> None:
    faculty = login(client, "faculty01")
    admin = login(client, "admin")
    booking = submit(client, faculty)
    entry = inbox_entry(client, admin, booking["id"])
    client.post(f"/approvals/{entry['step_id']}/reject", json={"comment": "Clashes with a visit"}, headers=admin)
    rows = client.get("/audit/approvals", headers=admin).json()["items"]
    rejected = next(row for row in rows if row["raw_action"] == "approval.rejected" and row["booking_id"] == booking["id"])
    assert rejected["action"] == "Rejected" and rejected["reason"] == "Clashes with a visit"
    assert rejected["actor_name"] and rejected["actor_id"] and rejected["at"]
    assert client.get("/audit/approvals", headers=faculty).status_code == 403
    own = client.get(f"/bookings/{booking['id']}/trail", headers=faculty).json()
    assert [row["action"] for row in own] == ["Submitted", "Rejected"]
    assert client.get(f"/bookings/{booking['id']}/trail", headers=login(client, "faculty02")).status_code == 403


def test_utilization_summary_comes_from_real_records(client, session) -> None:
    admin = login(client, "admin")
    faculty = login(client, "faculty01")
    before = client.get("/reports/utilization-summary", headers=admin).json()
    booking = submit(client, faculty, days=3)
    entry = inbox_entry(client, admin, booking["id"])
    client.post(f"/approvals/{entry['step_id']}/approve", json={}, headers=admin)
    after = client.get("/reports/utilization-summary", headers=admin).json()
    assert after["total_bookings"] == before["total_bookings"] + 1
    assert after["by_status"].get("CONFIRMED", 0) == before["by_status"].get("CONFIRMED", 0) + 1
    assert any(row["venue_id"] == booking["resource_id"] for row in after["most_used"])
    assert after["resources"]["rooms_total"] > 0 and after["vacant_now"]["count"] <= after["resources"]["rooms_available"]
    assert after["monthly"] and all(row["hours"] > 0 for row in after["monthly"])
    assert client.get("/reports/utilization-summary", headers=faculty).status_code == 403


def test_email_is_queued_only_when_smtp_is_configured_and_sent_after_commit(client, session, monkeypatch) -> None:
    sent: list[EmailMessage] = []
    monkeypatch.setattr(mailer, "deliver", lambda messages: sent.extend(messages))
    monkeypatch.setattr(mailer.pool, "submit", lambda function, messages: function(messages))
    faculty = login(client, "faculty01")
    submit(client, faculty, days=3)
    assert sent == []
    from app.config import get_settings
    settings = get_settings()
    patched = type(settings)(**{**settings.__dict__, "smtp_user": "sender@gmail.com", "smtp_pass": "abcdabcdabcdabcd", "smtp_from": "sender@gmail.com"})
    monkeypatch.setattr(mailer, "get_settings", lambda: patched)
    admin = login(client, "admin")
    booking = submit(client, faculty, days=4)
    recipients = {message["To"] for message in sent}
    assert "admin@jklu.demo" in recipients and "faculty01@jklu.demo" in recipients
    admin_mail = next(message for message in sent if message["To"] == "admin@jklu.demo")
    assert "New booking request" in admin_mail["Subject"]
    assert f"#{booking['id']}" in admin_mail.get_body(("plain",)).get_content()
    assert "text/html" in {part.get_content_type() for part in admin_mail.iter_parts()}
    entry = inbox_entry(client, admin, booking["id"])
    client.post(f"/approvals/{entry['step_id']}/reject", json={"comment": "Not available"}, headers=admin)
    rejection = next(message for message in sent if message["To"] == "faculty01@jklu.demo" and "rejected" in message["Subject"])
    assert "Not available" in rejection.get_body(("plain",)).get_content()


def test_smtp_failure_never_breaks_the_booking(client, session, monkeypatch) -> None:
    from app.config import get_settings
    settings = get_settings()
    patched = type(settings)(**{**settings.__dict__, "smtp_user": "sender@gmail.com", "smtp_pass": "abcdabcdabcdabcd", "smtp_from": "sender@gmail.com", "smtp_host": "127.0.0.1", "smtp_port": 1})
    monkeypatch.setattr(mailer, "get_settings", lambda: patched)
    monkeypatch.setattr(mailer.pool, "submit", lambda function, messages: function(messages))
    faculty = login(client, "faculty01")
    booking = submit(client, faculty, days=3)
    assert booking["status"] == "HELD"


def test_redirect_setting_sends_every_email_to_one_inbox(monkeypatch) -> None:
    from app.config import get_settings
    settings = get_settings()
    patched = type(settings)(**{**settings.__dict__, "smtp_user": "sender@gmail.com", "smtp_pass": "x", "smtp_from": "sender@gmail.com", "smtp_redirect_to": "me@gmail.com"})
    monkeypatch.setattr(mailer, "get_settings", lambda: patched)
    message = mailer.build_message("someone@jklu.demo", "Hello", "Body", [("Booking", "#1")])
    assert message["To"] == "me@gmail.com" and "someone@jklu.demo" in message["Subject"]


def test_deliver_uses_starttls_then_login_then_sends(monkeypatch) -> None:
    from app.config import get_settings
    settings = get_settings()
    patched = type(settings)(**{**settings.__dict__, "smtp_user": "sender@gmail.com", "smtp_pass": "abcdabcdabcdabcd", "smtp_from": "sender@gmail.com"})
    monkeypatch.setattr(mailer, "get_settings", lambda: patched)
    calls: list[tuple] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None) -> None:
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            calls.append(("quit",))

        def starttls(self) -> None:
            calls.append(("starttls",))

        def login(self, user, password) -> None:
            calls.append(("login", user, password))

        def send_message(self, message) -> None:
            calls.append(("send", message["To"], message["Subject"]))

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    message = mailer.build_message("user@example.com", "Booking #5 confirmed", "It is confirmed.", [("Booking", "#5")])
    mailer.deliver([message])
    assert [call[0] for call in calls] == ["connect", "starttls", "login", "send", "quit"]
    assert calls[0] == ("connect", "smtp.gmail.com", 587)
    assert calls[2] == ("login", "sender@gmail.com", "abcdabcdabcdabcd")
    assert calls[3] == ("send", "user@example.com", "Booking #5 confirmed")


def test_app_password_spaces_are_removed(monkeypatch) -> None:
    import app.config as config
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("SMTP_PASS", "abcd efgh ijkl mnop")
    settings = config.build_settings()
    assert settings.smtp_pass == "abcdefghijklmnop" and settings.smtp_from == "me@gmail.com" and settings.smtp_port == 587
