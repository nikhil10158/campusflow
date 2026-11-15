import hashlib
import hmac
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import select

from app import db
from app.config import get_settings
from app.deps import AdminUser, CurrentUser, SessionDep
from app.engine import batch
from app.engine.search import SearchRequest, search_free_rooms
from app.models import tables as t
from app.models.schemas import BatchIn, DemoNowIn
from app.rules import load_rules
from app.seed import load
from app.services import approvals, audit, calendar, clock, race
from app.services.config import solver_settings
from app.services.snapshot import get_index

router = APIRouter(tags=["admin"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(response: Response) -> dict:
    seeded = load.is_seeded()
    if not seeded:
        response.status_code = 503
    return {"ready": seeded}


@router.get("/demo/now")
def demo_now(session: SessionDep, user: CurrentUser) -> dict:
    return {"now": clock.get_now(session).isoformat()}


@router.post("/demo/now")
def set_demo_now(payload: DemoNowIn, session: SessionDep, user: AdminUser) -> dict:
    clock.set_now(session, payload.now)
    audit.append(session, user.email, "demo.clock_changed", {"now": payload.now.isoformat()})
    session.commit()
    maintenance = approvals.run_maintenance(session, payload.now)
    return {"now": payload.now.isoformat(), **maintenance}


@router.post("/demo/reset")
def reset_demo(user: AdminUser) -> dict:
    load.seed_database(rebuild=True)
    return {"status": "reset"}


@router.get("/audit")
def audit_log(session: SessionDep, user: AdminUser, limit: int = 200, action: str | None = None, actor: str | None = None, offset: int = 0) -> dict:
    query = select(t.AuditLog).order_by(t.AuditLog.id.desc())
    if action:
        query = query.where(t.AuditLog.action.contains(action))
    if actor:
        query = query.where(t.AuditLog.actor.contains(actor))
    rows = session.exec(query.offset(offset).limit(min(limit, 1000))).all()
    return {"items": [{"id": r.id, "ts": r.ts.isoformat(), "actor": r.actor, "action": r.action, "detail": r.detail, "hash": r.hash, "prev_hash": r.prev_hash} for r in rows]}


@router.get("/audit/verify")
def audit_verify(session: SessionDep, user: AdminUser) -> dict:
    return audit.verify(session)


@router.get("/outbox")
def outbox(session: SessionDep, user: CurrentUser, limit: int = 100) -> list[dict]:
    query = select(t.Notification).order_by(t.Notification.id.desc()).limit(limit)
    if user.role != "admin":
        query = query.where(t.Notification.recipient == user.email)
    return [{"id": n.id, "channel": n.channel, "recipient": n.recipient, "subject": n.subject, "body": n.body, "created_at": n.created_at.isoformat(), "booking_id": n.related_booking_id} for n in session.exec(query)]


def feed_token(user_id: int) -> str:
    return hmac.new(get_settings().pass_secret.encode(), f"ics-{user_id}".encode(), hashlib.sha256).hexdigest()[:24]


@router.get("/ics/token")
def ics_token(user: CurrentUser) -> dict:
    return {"user_id": user.id, "token": feed_token(user.id), "url": f"/ics/users/{user.id}.ics?token={feed_token(user.id)}"}


@router.get("/ics/venues/{code}.ics")
def venue_ics(code: str, session: SessionDep) -> Response:
    events = session.exec(select(t.CalendarEvent).where(t.CalendarEvent.venue_code == code).order_by(t.CalendarEvent.start_dt)).all()
    return Response(calendar.to_ics(f"{code} schedule", list(events), redact=True), media_type="text/calendar")


@router.get("/ics/users/{user_id}.ics")
def user_ics(user_id: int, token: str, session: SessionDep) -> Response:
    if not hmac.compare_digest(token, feed_token(user_id)):
        raise HTTPException(status_code=403, detail="Bad calendar token")
    events = session.exec(select(t.CalendarEvent).where(t.CalendarEvent.owner_id == user_id).order_by(t.CalendarEvent.start_dt)).all()
    return Response(calendar.to_ics("My CampusFlow bookings", list(events)), media_type="text/calendar")


@router.post("/mock/calendar/events")
def mock_calendar_event(payload: dict, session: SessionDep, user: AdminUser) -> dict:
    event = t.CalendarEvent(title=str(payload.get("title", "Mock event")), start_dt=datetime.fromisoformat(payload["start"]), end_dt=datetime.fromisoformat(payload["end"]), venue_code=payload.get("venue_code"), owner_id=user.id)
    session.add(event)
    session.commit()
    return {"id": event.id}


@router.post("/batch/optimise")
def optimise(payload: BatchIn, session: SessionDep, user: AdminUser) -> dict:
    index = get_index(session)
    limits = solver_settings()
    events = batch.build_events(index, load_rules(), min(payload.events, 60), payload.seed, payload.first_day)
    return batch.compare(index, load_rules(), events, limits["time_limit"], limits["workers"])


@router.get("/benchmark/run")
def benchmark(session: SessionDep, user: AdminUser, events: int = 25) -> dict:
    index = get_index(session)
    rules = load_rules()
    first = date.fromisoformat("2026-11-17")
    latencies = []
    for count in (1, 3, 7):
        windows = [(datetime(2026, 11, 17, 10) + timedelta(days=n), datetime(2026, 11, 17, 11) + timedelta(days=n)) for n in range(count)]
        samples = []
        for _ in range(20):
            began = time.perf_counter()
            search_free_rooms(index, SearchRequest(windows=windows, attendees=40, types=["classroom", "seminar_hall", "lab", "amphitheatre"]), rules)
            samples.append((time.perf_counter() - began) * 1000)
        samples.sort()
        latencies.append({"days": count, "p50_ms": round(samples[len(samples) // 2], 2), "p95_ms": round(samples[int(len(samples) * 0.95)], 2)})
    limits = solver_settings()
    scenario = batch.compare(index, rules, batch.build_events(index, rules, events, 7, date(2026, 12, 1)), limits["time_limit"], limits["workers"])
    return {"search_latency": latencies, "venues": len(index.snapshot.venues), "batch": scenario}


@router.post("/simulate/race")
def simulate_race(user: AdminUser, racers: int = 20) -> dict:
    return race.run_race(min(max(racers, 2), 40))
