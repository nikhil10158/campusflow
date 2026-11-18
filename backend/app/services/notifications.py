from datetime import datetime

from sqlmodel import Session, select

from app.models.tables import Notification, User, UserNotification
from app.services import mailer


def notify(session: Session, recipient: User | str, subject: str, body: str, now: datetime, booking_id: int | None = None, channels: tuple[str, ...] = ("email",), kind: str = "booking") -> None:
    address = recipient.email if isinstance(recipient, User) else recipient
    for channel in channels:
        session.add(Notification(channel=channel, recipient=address, subject=subject, body=body, created_at=now, related_booking_id=booking_id))
    if isinstance(recipient, User) and recipient.id is not None:
        session.add(UserNotification(user_id=recipient.id, kind=kind, title=subject, body=body, booking_id=booking_id, created_at=now))
    if "email" in channels:
        mailer.queue(session, address, subject, body, booking_id)


def notify_admins(session: Session, subject: str, body: str, now: datetime, booking_id: int | None = None, skip_user_id: int | None = None) -> int:
    sent = 0
    for admin in session.exec(select(User).where(User.role == "admin")).all():
        if admin.id == skip_user_id:
            continue
        notify(session, admin, subject, body, now, booking_id, kind="new_request")
        sent += 1
    return sent
