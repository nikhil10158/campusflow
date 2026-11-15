import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Date, DateTime, insert
from sqlmodel import Session, select

from app import db
from app.config import DATA_DIR
from app.models.tables import ALL_TABLES, Booking, CalendarEvent, Venue
from app.seed.campus import SCALE
from app.seed.world import build_world
from app.services import audit, passes
from app.services.auth import hash_password
from app.services.snapshot import reset_cache

DEMO_PASSWORD = "Demo@1234"
BASELINE_PATH = DATA_DIR / "seed" / "baseline.json"
LOAD_ORDER = [
    "building", "venue", "term", "holiday", "section", "faculty", "course", "user", "timetableversion", "timetableentry",
    "scheduleexception", "bookingbundle", "booking", "approvalstep", "maintenance", "guest", "guestroom", "parkinglot", "occupancysample",
]


def encode(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def dump_rows(rows: dict[str, list[dict]], path: Path = BASELINE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({name: [{k: encode(v) for k, v in row.items()} for row in items] for name, items in rows.items()}), encoding="utf-8")


def decode_row(table, row: dict) -> dict:
    decoded = dict(row)
    for column in table.columns:
        value = decoded.get(column.name)
        if isinstance(value, str) and isinstance(column.type, DateTime):
            decoded[column.name] = datetime.fromisoformat(value)
        elif isinstance(value, str) and isinstance(column.type, Date):
            decoded[column.name] = date.fromisoformat(value)
    return decoded


def insert_rows(session: Session, rows: dict[str, list[dict]]) -> None:
    tables = {model.__tablename__: model.__table__ for model in ALL_TABLES}
    for name in LOAD_ORDER:
        items = rows.get(name, [])
        for start in range(0, len(items), 2000):
            session.execute(insert(tables[name]), [decode_row(tables[name], row) for row in items[start:start + 2000]])


def finalise_confirmed(session: Session) -> None:
    for booking in session.exec(select(Booking).where(Booking.status == "CONFIRMED")):
        passes.issue_for_booking(session, booking)
        venue = session.get(Venue, booking.resource_id) if booking.resource_type == "venue" else None
        session.add(CalendarEvent(booking_id=booking.id, venue_code=venue.code if venue else None, owner_id=booking.requester_id, title=booking.event_title, start_dt=booking.start_dt, end_dt=booking.end_dt))


def load_world(session: Session, rows: dict[str, list[dict]]) -> None:
    insert_rows(session, rows)
    session.flush()
    finalise_confirmed(session)
    audit.append(session, "system", "seed.loaded", {"venues": len(rows["venue"]), "timetable_entries": len(rows["timetableentry"]), "bookings": len(rows["booking"])})


def generate_rows() -> dict[str, list[dict]]:
    return build_world(hash_password(DEMO_PASSWORD))


def load_rows() -> dict[str, list[dict]]:
    if BASELINE_PATH.exists() and SCALE == 1:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return generate_rows()


def seed_database(rebuild: bool = False) -> None:
    engine = db.get_engine()
    if rebuild:
        db.drop_schema(engine)
    db.create_schema(engine)
    with Session(engine) as session:
        if session.exec(select(Venue)).first() is None:
            load_world(session, load_rows())
            session.commit()
    reset_cache()


def is_seeded() -> bool:
    try:
        with Session(db.get_engine()) as session:
            return session.exec(select(Venue)).first() is not None
    except Exception:
        return False


def ensure_seeded() -> None:
    if not is_seeded():
        seed_database()
