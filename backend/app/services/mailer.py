import logging
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from html import escape

from sqlalchemy import event
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Session, select

from app.config import get_settings
from app.models import tables as t
from app.services.tracker import track_label, track_status

logger = logging.getLogger("campusflow.mail")
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mail")
PENDING_KEY = "pending_emails"


def configured() -> bool:
    settings = get_settings()
    return bool(settings.smtp_user and settings.smtp_pass)


def resource_label(session: Session, booking: t.Booking) -> str:
    if booking.resource_type == "venue":
        row = session.get(t.Venue, booking.resource_id)
        return row.code if row else f"Venue {booking.resource_id}"
    if booking.resource_type == "guest_room":
        row = session.get(t.GuestRoom, booking.resource_id)
        return f"Guest room {row.code}" if row else f"Guest room {booking.resource_id}"
    row = session.get(t.ParkingLot, booking.resource_id)
    return row.name if row else f"Parking lot {booking.resource_id}"


def booking_details(session: Session, booking_id: int | None) -> list[tuple[str, str]]:
    booking = session.get(t.Booking, booking_id) if booking_id else None
    if booking is None:
        return []
    rows = [
        ("Booking", f"#{booking.id}"),
        ("Title", booking.event_title),
        ("Resource", resource_label(session, booking)),
        ("When", f"{booking.start_dt:%a %d %b %Y, %H:%M} to {booking.end_dt:%a %d %b %Y, %H:%M}"),
        ("Status", track_label(track_status(session, booking))),
    ]
    if booking.status == "REJECTED":
        steps = session.exec(select(t.ApprovalStep).where(t.ApprovalStep.booking_id == booking.id, t.ApprovalStep.status == "REJECTED")).all()
        reason = next((step.comment for step in steps if step.comment), "")
        if reason:
            rows.append(("Reason", reason))
    return rows


def build_message(recipient: str, subject: str, body: str, details: list[tuple[str, str]]) -> EmailMessage:
    settings = get_settings()
    target = settings.smtp_redirect_to or recipient
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = target
    message["Subject"] = f"{subject} (for {recipient})" if settings.smtp_redirect_to and recipient != target else subject
    text = body + "".join(f"\n{label}: {value}" for label, value in details) + "\n\nCampusFlow demo (synthetic data)."
    rows = "".join(f"<tr><td style='padding:4px 12px 4px 0;color:#5d6b8a'>{escape(label)}</td><td style='padding:4px 0'><b>{escape(value)}</b></td></tr>" for label, value in details)
    html = (
        "<div style='font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#0e1330'>"
        "<div style='background:#0b1020;color:#fff;padding:14px 18px;border-radius:10px 10px 0 0;font-weight:bold'>CampusFlow</div>"
        "<div style='border:1px solid #dce1f5;border-top:0;padding:18px;border-radius:0 0 10px 10px'>"
        f"<h2 style='margin:0 0 8px'>{escape(subject)}</h2><p style='margin:0 0 12px'>{escape(body)}</p>"
        f"<table style='border-collapse:collapse'>{rows}</table>"
        "<p style='color:#5d6b8a;font-size:12px;margin-top:16px'>CampusFlow demo (synthetic data).</p></div></div>"
    )
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    return message


def deliver(messages: list[EmailMessage]) -> None:
    settings = get_settings()
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            for message in messages:
                server.send_message(message)
    except Exception as problem:
        logger.warning("Email not sent: %s", problem)


def queue(session: Session, recipient: str, subject: str, body: str, booking_id: int | None) -> None:
    if not configured() or not recipient:
        return
    message = build_message(recipient, subject, body, booking_details(session, booking_id))
    session.info.setdefault(PENDING_KEY, []).append(message)


@event.listens_for(OrmSession, "after_commit")
def send_after_commit(session) -> None:
    messages = session.info.pop(PENDING_KEY, None)
    if messages:
        pool.submit(deliver, messages)


@event.listens_for(OrmSession, "after_rollback")
def forget_after_rollback(session) -> None:
    session.info.pop(PENDING_KEY, None)
