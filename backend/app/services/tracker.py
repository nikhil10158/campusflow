from sqlmodel import Session, select

from app.models import tables as t

LABELS = {
    "PENDING": "Pending",
    "UNDER_REVIEW": "Under Review",
    "APPROVED": "Approved",
    "REJECTED": "Rejected",
}


def track_status(session: Session, booking: t.Booking) -> str:
    if booking.status == "CONFIRMED":
        return "APPROVED"
    if booking.status == "REJECTED":
        return "REJECTED"
    if booking.status != "HELD":
        return booking.status
    steps = session.exec(select(t.ApprovalStep).where(t.ApprovalStep.booking_id == booking.id)).all()
    if any(step.status in ("APPROVED", "ESCALATED") for step in steps):
        return "UNDER_REVIEW"
    return "PENDING"


def track_label(status: str) -> str:
    return LABELS.get(status, status.replace("_", " ").title())
