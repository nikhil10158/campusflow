from sqlmodel import Session, select

from app.engine.alternatives import recommend_alternatives
from app.models import tables as t
from app.models.schemas import BookingIn, RecoveryResubmitIn
from app.rules import load_rules
from app.services import audit, bookings
from app.services.bookings import get_booking, request_from_booking, visible_to
from app.services.errors import Conflict, Forbidden
from app.services.mailer import resource_label
from app.services.snapshot import fresh_index

ALTERNATIVE_LIMIT = 8


def rejection_of(session: Session, booking: t.Booking) -> dict:
    steps = session.exec(select(t.ApprovalStep).where(t.ApprovalStep.booking_id == booking.id, t.ApprovalStep.status == "REJECTED")).all()
    step = steps[0] if steps else None
    approver = session.get(t.User, step.approver_id) if step and step.approver_id else None
    return {
        "reason": step.comment if step else "",
        "scope": step.scope if step else None,
        "by": approver.name or approver.email if approver else None,
        "by_id": approver.id if approver else None,
        "at": step.decided_at.isoformat() if step and step.decided_at else None,
    }


def successor_of(session: Session, booking: t.Booking) -> t.Booking | None:
    rows = session.exec(select(t.Booking).where(t.Booking.requester_id == booking.requester_id, t.Booking.id > booking.id)).all()
    return next((row for row in rows if row.meta_json.get("resubmitted_from") == booking.id and row.status in ("HELD", "CONFIRMED")), None)


def require_view(user: t.User, booking: t.Booking) -> None:
    if not visible_to(user, booking):
        raise Forbidden("Only the requester, the sponsor or an administrator may see this")


def original_of(session: Session, booking: t.Booking) -> dict:
    return {
        "resource_type": booking.resource_type, "resource_id": booking.resource_id, "resource_label": resource_label(session, booking),
        "start": booking.start_dt.isoformat(), "end": booking.end_dt.isoformat(), "event_title": booking.event_title, "purpose": booking.purpose,
        "attendees": booking.attendees, "qty": booking.qty, "sponsor_id": booking.sponsor_id,
    }


def recovery_view(session: Session, user: t.User, booking_id: int) -> dict:
    booking = get_booking(session, booking_id)
    require_view(user, booking)
    if booking.status != "REJECTED":
        raise Conflict(f"Booking is {booking.status}; only rejected requests have recovery options")
    rules = load_rules()
    index = fresh_index(session)
    request = request_from_booking(session, booking)
    options = []
    for option in recommend_alternatives(index, rules, request, ALTERNATIVE_LIMIT):
        body = option.as_dict(index.snapshot)
        first = body["parts"][0] if body["parts"] else None
        body["same_time"] = bool(first and first["start"] == booking.start_dt.isoformat() and first["end"] == booking.end_dt.isoformat())
        body["same_type"] = bool(first and first["resource_type"] == booking.resource_type)
        options.append(body)
    options.sort(key=lambda item: (not item["same_time"], item["cost"]))
    successor = successor_of(session, booking)
    return {
        "booking_id": booking.id, "rejection": rejection_of(session, booking), "original": original_of(session, booking),
        "alternatives": options, "resubmitted_as": successor.id if successor else None,
    }


def resubmit(session: Session, user: t.User, booking_id: int, choice: RecoveryResubmitIn) -> dict:
    booking = get_booking(session, booking_id)
    if booking.requester_id != user.id:
        raise Forbidden("Only the person who made the request can resubmit it")
    if booking.status != "REJECTED":
        raise Conflict(f"Booking is {booking.status}; only rejected requests can be resubmitted")
    existing = successor_of(session, booking)
    if existing is not None:
        raise Conflict(f"This request was already resubmitted as #{existing.id}")
    meta = {key: value for key, value in booking.meta_json.items() if key not in ("exclude_booking_id", "requester_dept")}
    meta["resubmitted_from"] = booking.id
    payload = BookingIn(
        resource_type=booking.resource_type, resource_id=choice.resource_id or booking.resource_id, start=choice.start or booking.start_dt, end=choice.end or booking.end_dt,
        event_title=booking.event_title, purpose=booking.purpose, attendees=booking.attendees, qty=booking.qty, sponsor_id=booking.sponsor_id,
        host_ref=booking.meta_json.get("host"), meta=meta,
    )
    created = bookings.submit_booking(session, user, payload)
    audit.append(session, user.email, "booking.resubmitted", {"booking_id": created.id, "from_booking_id": booking.id})
    session.commit()
    return bookings.booking_dict(session, created, user)
