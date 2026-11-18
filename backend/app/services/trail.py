from sqlmodel import Session, select

from app.models import tables as t
from app.services.bookings import get_booking, visible_to
from app.services.errors import Forbidden
from app.services.mailer import resource_label

LABELS = {
    "booking.submitted": "Submitted",
    "booking.resubmitted": "Resubmitted",
    "approval.approved": "Approved",
    "approval.rejected": "Rejected",
    "approval.stale": "Updated",
    "approval.escalated": "Escalated",
    "booking.confirmed": "Confirmed",
    "booking.moved": "Updated",
    "booking.cancelled": "Cancelled",
    "booking.expired": "Expired",
}


def entries_for(session: Session, booking_ids: set[int] | None, limit: int, offset: int = 0) -> list[dict]:
    rows = session.exec(select(t.AuditLog).where(t.AuditLog.action.in_(list(LABELS))).order_by(t.AuditLog.id.desc())).all()
    chosen = [row for row in rows if row.detail.get("booking_id") is not None and (booking_ids is None or row.detail["booking_id"] in booking_ids)]
    page = chosen[offset:offset + limit]
    users = {user.email: user for user in session.exec(select(t.User)).all()}
    booking_cache: dict[int, t.Booking | None] = {}
    items = []
    for row in page:
        booking_id = row.detail["booking_id"]
        if booking_id not in booking_cache:
            booking_cache[booking_id] = session.get(t.Booking, booking_id)
        booking = booking_cache[booking_id]
        actor = users.get(row.actor)
        reason = row.detail.get("reason") or row.detail.get("change") or ""
        if row.action == "approval.stale":
            reason = "; ".join(row.detail.get("conflicts", []))
        items.append({
            "id": row.id, "at": row.ts.isoformat(), "action": LABELS[row.action], "raw_action": row.action, "booking_id": booking_id,
            "booking_title": booking.event_title if booking else None, "resource": resource_label(session, booking) if booking else None,
            "actor": row.actor, "actor_name": actor.name if actor else ("System" if row.actor == "system" else row.actor), "actor_id": actor.id if actor else None,
            "reason": reason, "scope": row.detail.get("scope"),
        })
    return items


def booking_trail(session: Session, user: t.User, booking_id: int) -> list[dict]:
    booking = get_booking(session, booking_id)
    if not (visible_to(user, booking) or user.role == "approver"):
        raise Forbidden("You can only see the trail of your own requests")
    return list(reversed(entries_for(session, {booking_id}, 200)))


def approval_trail(session: Session, limit: int, offset: int) -> list[dict]:
    return entries_for(session, None, min(limit, 500), offset)
