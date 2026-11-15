from datetime import datetime

from sqlmodel import Session

from app.models.tables import Notification, User


def notify(session: Session, recipient: User | str, subject: str, body: str, now: datetime, booking_id: int | None = None, channels: tuple[str, ...] = ("email",)) -> None:
    address = recipient.email if isinstance(recipient, User) else recipient
    for channel in channels:
        session.add(Notification(channel=channel, recipient=address, subject=subject, body=body, created_at=now, related_booking_id=booking_id))
