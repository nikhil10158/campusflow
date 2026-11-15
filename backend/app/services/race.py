import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlmodel import Session, select

from app import db
from app.engine import validator
from app.engine.search import SearchRequest, search_free_rooms
from app.models import tables as t
from app.models.schemas import BookingIn
from app.rules import load_rules
from app.services import approvals
from app.services.bookings import submit_booking
from app.services.errors import Conflict, ServiceError
from app.services.snapshot import fresh_index, load_snapshot

RACE_TITLE = "Race simulation booking"


def pick_target(session: Session) -> tuple[int, str, str]:
    index = fresh_index(session)
    day = (index.snapshot.now + timedelta(days=3)).replace(hour=11, minute=0, second=0, microsecond=0)
    window = (day, day + timedelta(hours=1))
    outcome = search_free_rooms(index, SearchRequest(windows=[window], attendees=40, types=["classroom"]), load_rules())
    if not outcome.hits:
        raise ServiceError("No free classroom found for the race")
    return outcome.hits[0].venue.id, window[0].isoformat(), window[1].isoformat()


def racer(number: int, user_id: int, admin_id: int, venue_id: int, start: str, end: str) -> str:
    payload = BookingIn.model_validate({"resource_type": "venue", "resource_id": venue_id, "start": start, "end": end, "event_title": RACE_TITLE, "attendees": 40})
    try:
        with db.session_scope(write=True) as session:
            user = session.get(t.User, user_id)
            booking = submit_booking(session, user, payload)
            booking_id = booking.id
        with db.session_scope(write=True) as session:
            admin = session.get(t.User, admin_id)
            for step in approvals.steps_of(session, booking_id):
                approvals.decide(session, admin, step.id, True, "race approval")
            return "confirmed" if session.get(t.Booking, booking_id).status == "CONFIRMED" else "held"
    except Conflict:
        return "conflict"
    except ServiceError as error:
        return f"error: {error.message}"


def run_race(racers: int = 20) -> dict:
    with Session(db.get_engine()) as session:
        venue_id, start, end = pick_target(session)
        faculty_ids = [u.id for u in session.exec(select(t.User).where(t.User.role == "faculty"))]
        admin_id = session.exec(select(t.User).where(t.User.role == "admin")).first().id
    began = time.perf_counter()
    with ThreadPoolExecutor(max_workers=racers) as pool:
        futures = [pool.submit(racer, n, faculty_ids[n % len(faculty_ids)], admin_id, venue_id, start, end) for n in range(racers)]
        outcomes = [f.result() for f in futures]
    elapsed = (time.perf_counter() - began) * 1000
    with Session(db.get_engine()) as session:
        violations = validator.validate(load_snapshot(session, with_ghosts=False), load_rules())
        venue = session.get(t.Venue, venue_id)
    return {
        "venue": venue.code, "start": start, "end": end, "racers": racers, "winners": outcomes.count("confirmed"), "conflicts": outcomes.count("conflict"),
        "other": [o for o in outcomes if o not in ("confirmed", "conflict")], "validator_violations": [v.as_dict() for v in violations], "elapsed_ms": round(elapsed),
    }
