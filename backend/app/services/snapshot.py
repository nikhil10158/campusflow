from dataclasses import fields
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import event
from sqlmodel import Session, select

from app.engine.availability import AvailabilityIndex
from app.engine.ghost import detect_ghosts
from app.engine.types import (
    BookingInfo, BuildingInfo, EntryInfo, ExceptionInfo, GuestRoomInfo, LotInfo, MaintenanceInfo, PassInfo,
    SectionInfo, Snapshot, StepInfo, VenueInfo,
)
from app.models import tables as t
from app.rules import load_rules
from app.services.clock import get_now

INDEX_HORIZON_DAYS = 150
WATCHED_TABLES = (
    t.Booking, t.TimetableEntry, t.TimetableVersion, t.ScheduleException, t.Maintenance, t.Holiday, t.Venue,
    t.Setting, t.GuestRoom, t.ParkingLot, t.ApprovalStep, t.Pass, t.Section, t.OccupancySample,
)

version_counter = 0
cache: dict[str, Any] = {}


def bump_version() -> None:
    global version_counter
    version_counter += 1


def reset_cache() -> None:
    cache.clear()
    bump_version()


@event.listens_for(Session, "after_flush")
def watch_flushes(session: Session, _context: Any) -> None:
    changed = list(session.new) + list(session.dirty) + list(session.deleted)
    if any(isinstance(obj, WATCHED_TABLES) for obj in changed):
        session.info["bump_after_commit"] = True


@event.listens_for(Session, "after_commit")
def bump_after_commit(session: Session) -> None:
    if session.info.pop("bump_after_commit", False):
        bump_version()


@event.listens_for(Session, "after_rollback")
def forget_bump(session: Session) -> None:
    session.info.pop("bump_after_commit", None)


def convert(cls: type, row: Any, **extra: Any) -> Any:
    values: dict[str, Any] = {}
    for item in fields(cls):
        if item.name in extra:
            continue
        value = getattr(row, item.name)
        values[item.name] = tuple(value) if isinstance(value, list) else value
    values.update(extra)
    return cls(**values)


def load_snapshot(session: Session, with_ghosts: bool = True, exclude_booking_ids: frozenset[int] = frozenset()) -> Snapshot:
    now = get_now(session)
    active = [v.id for v in session.exec(select(t.TimetableVersion).where(t.TimetableVersion.status == "ACTIVE"))]
    snapshot = Snapshot(now=now, version=version_counter)
    snapshot.venues = [convert(VenueInfo, v) for v in session.exec(select(t.Venue).order_by(t.Venue.id))]
    snapshot.buildings = {b.id: convert(BuildingInfo, b) for b in session.exec(select(t.Building))}
    snapshot.sections = {s.id: convert(SectionInfo, s) for s in session.exec(select(t.Section))}
    snapshot.faculty = {f.id: f.name for f in session.exec(select(t.Faculty))}
    snapshot.entries = [convert(EntryInfo, e) for e in session.exec(select(t.TimetableEntry).where(t.TimetableEntry.version_id.in_(active)))] if active else []
    live_entries = {e.id for e in snapshot.entries}
    snapshot.exceptions = [convert(ExceptionInfo, e) for e in session.exec(select(t.ScheduleException)) if e.entry_id in live_entries]
    snapshot.holidays = {h.date for h in session.exec(select(t.Holiday))}
    snapshot.bookings = [convert(BookingInfo, b, meta=b.meta_json) for b in session.exec(select(t.Booking)) if b.id not in exclude_booking_ids]
    snapshot.maintenance = [convert(MaintenanceInfo, m) for m in session.exec(select(t.Maintenance))]
    snapshot.guest_rooms = [convert(GuestRoomInfo, g) for g in session.exec(select(t.GuestRoom).order_by(t.GuestRoom.id))]
    snapshot.lots = [convert(LotInfo, p, near=p.near_json) for p in session.exec(select(t.ParkingLot).order_by(t.ParkingLot.id))]
    snapshot.steps = [convert(StepInfo, s) for s in session.exec(select(t.ApprovalStep))]
    snapshot.passes = [convert(PassInfo, p) for p in session.exec(select(t.Pass))]
    if with_ghosts:
        samples = {(s.venue_id, s.ts_hour): s.headcount for s in session.exec(select(t.OccupancySample))}
        snapshot.ghost_entry_ids = {g.entry.id for g in detect_ghosts(snapshot, samples, load_rules(), now.date())}
    return snapshot


def horizon(session: Session, now: datetime) -> tuple[date, date]:
    term = session.exec(select(t.Term).order_by(t.Term.start)).first()
    first = term.start if term else now.date() - timedelta(days=100)
    last = max(term.end if term else now.date(), now.date() + timedelta(days=INDEX_HORIZON_DAYS))
    return first, last


def get_index(session: Session) -> AvailabilityIndex:
    now = get_now(session)
    key = (str(session.get_bind().url), version_counter, now)
    if cache.get("key") != key:
        snapshot = load_snapshot(session)
        first, last = horizon(session, now)
        cache["key"] = key
        cache["index"] = AvailabilityIndex(snapshot, first, last)
    return cache["index"]


def get_snapshot(session: Session) -> Snapshot:
    return get_index(session).snapshot


def fresh_index(session: Session, exclude_booking_ids: frozenset[int] = frozenset()) -> AvailabilityIndex:
    snapshot = load_snapshot(session, with_ghosts=False, exclude_booking_ids=exclude_booking_ids)
    first, last = horizon(session, snapshot.now)
    return AvailabilityIndex(snapshot, first, last)
