from datetime import datetime

from sqlmodel import Session

from app.config import get_settings
from app.models.tables import Setting

DEMO_NOW_KEY = "demo_now"


def get_now(session: Session) -> datetime:
    row = session.get(Setting, DEMO_NOW_KEY)
    return datetime.fromisoformat(row.value) if row else get_settings().demo_now


def set_now(session: Session, value: datetime) -> None:
    row = session.get(Setting, DEMO_NOW_KEY)
    if row is None:
        session.add(Setting(key=DEMO_NOW_KEY, value=value.isoformat()))
    else:
        row.value = value.isoformat()
        session.add(row)
    session.flush()
