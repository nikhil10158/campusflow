from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.deps import CurrentUser, SessionDep
from app.engine.availability import entry_label
from app.models import tables as t
from app.rules import load_rules
from app.services.clock import get_now
from app.services.snapshot import get_index

router = APIRouter(tags=["reference"])


@router.get("/venues")
def venues(session: SessionDep, user: CurrentUser, type: str | None = None) -> list[t.Venue]:
    query = select(t.Venue).order_by(t.Venue.id)
    if type:
        query = query.where(t.Venue.type == type)
    return list(session.exec(query))


@router.get("/buildings")
def buildings(session: SessionDep, user: CurrentUser) -> list[t.Building]:
    return list(session.exec(select(t.Building).order_by(t.Building.id)))


@router.get("/sections")
def sections(session: SessionDep, user: CurrentUser) -> list[t.Section]:
    return list(session.exec(select(t.Section).order_by(t.Section.id)))


@router.get("/faculty")
def faculty(session: SessionDep, user: CurrentUser) -> list[t.Faculty]:
    return list(session.exec(select(t.Faculty).order_by(t.Faculty.id)))


@router.get("/guest-rooms")
def guest_rooms(session: SessionDep, user: CurrentUser) -> list[t.GuestRoom]:
    return list(session.exec(select(t.GuestRoom).order_by(t.GuestRoom.id)))


@router.get("/parking-lots")
def parking_lots(session: SessionDep, user: CurrentUser) -> list[t.ParkingLot]:
    return list(session.exec(select(t.ParkingLot).order_by(t.ParkingLot.id)))


@router.get("/holidays")
def holidays(session: SessionDep, user: CurrentUser) -> list[t.Holiday]:
    return list(session.exec(select(t.Holiday).order_by(t.Holiday.date)))


@router.get("/term")
def term(session: SessionDep, user: CurrentUser) -> dict:
    row = session.exec(select(t.Term)).first()
    return {"id": row.id, "name": row.name, "start": row.start.isoformat(), "end": row.end.isoformat(), "now": get_now(session).isoformat()}


@router.get("/timetable/sections/{section_id}")
def section_timetable(section_id: int, session: SessionDep, user: CurrentUser, week_of: date | None = None) -> dict:
    index = get_index(session)
    snapshot = index.snapshot
    section = snapshot.sections.get(section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    monday = (week_of or snapshot.now.date()) - timedelta(days=(week_of or snapshot.now.date()).weekday())
    cleared = {(e.entry_id, e.date): e.type for e in snapshot.exceptions if e.status == "APPROVED"}
    rows = []
    for entry in snapshot.entries:
        if entry.section_id != section_id:
            continue
        day = monday + timedelta(days=entry.weekday)
        rows.append({
            "entry_id": entry.id, "weekday": entry.weekday, "date": day.isoformat(), "start_min": entry.start_min, "end_min": entry.end_min,
            "course_code": entry.course_code, "course_name": entry.course_name, "kind": entry.kind, "venue_code": snapshot.venue(entry.venue_id).code,
            "venue_id": entry.venue_id, "faculty": snapshot.faculty.get(entry.faculty_id, ""), "exception": cleared.get((entry.id, day)),
            "holiday": day in snapshot.holidays,
        })
    return {"section": {"id": section.id, "dept": section.dept, "semester": section.semester, "name": section.name, "size": section.size}, "week_start": monday.isoformat(), "entries": rows, "periods": load_rules().periods}


@router.get("/timetable/venues/{venue_id}")
def venue_timetable(venue_id: int, session: SessionDep, user: CurrentUser) -> list[dict]:
    snapshot = get_index(session).snapshot
    return [
        {"entry_id": e.id, "weekday": e.weekday, "start_min": e.start_min, "end_min": e.end_min, "label": entry_label(snapshot, e) if user.role == "admin" else "Busy", "kind": e.kind}
        for e in snapshot.entries if e.venue_id == venue_id
    ]
