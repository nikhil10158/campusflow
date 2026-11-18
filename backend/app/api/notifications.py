
from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import select

from app.deps import CurrentUser, SessionDep
from app.models import tables as t
from app.services.clock import get_now
from app.services.errors import NotFound

router = APIRouter(tags=["notifications"])


def item_of(row: t.UserNotification) -> dict:
    return {"id": row.id, "kind": row.kind, "title": row.title, "body": row.body, "booking_id": row.booking_id, "read": row.read_at is not None, "created_at": row.created_at.isoformat()}


def unread_count(session: SessionDep, user: t.User) -> int:
    return session.exec(select(func.count()).select_from(t.UserNotification).where(t.UserNotification.user_id == user.id, t.UserNotification.read_at.is_(None))).one()


@router.get("/notifications")
def list_notifications(session: SessionDep, user: CurrentUser, limit: int = 40, unread_only: bool = False) -> dict:
    query = select(t.UserNotification).where(t.UserNotification.user_id == user.id)
    if unread_only:
        query = query.where(t.UserNotification.read_at.is_(None))
    rows = session.exec(query.order_by(t.UserNotification.id.desc()).limit(min(limit, 200))).all()
    return {"items": [item_of(row) for row in rows], "unread": unread_count(session, user)}


@router.post("/notifications/read-all")
def mark_all_read(session: SessionDep, user: CurrentUser) -> dict:
    now = get_now(session)
    for row in session.exec(select(t.UserNotification).where(t.UserNotification.user_id == user.id, t.UserNotification.read_at.is_(None))).all():
        row.read_at = now
        session.add(row)
    session.commit()
    return {"unread": 0}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, session: SessionDep, user: CurrentUser) -> dict:
    row = session.get(t.UserNotification, notification_id)
    if row is None or row.user_id != user.id:
        raise NotFound("Notification not found")
    if row.read_at is None:
        row.read_at = get_now(session)
        session.add(row)
        session.commit()
    return {"unread": unread_count(session, user)}
