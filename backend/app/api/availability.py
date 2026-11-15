from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.deps import CurrentUser, SessionDep
from app.engine import explain
from app.engine.alternatives import recommend_alternatives
from app.engine.cohort import CohortRequest, find_common_slots
from app.engine.search import SearchRequest, search_free_rooms
from app.engine.utilisation import free_room_heatmap
from app.models import tables as t
from app.models.schemas import BookingIn, CohortIn
from app.rules import load_rules
from app.services.bookings import alternatives_payload, to_request
from app.services.snapshot import get_index

router = APIRouter(prefix="/availability", tags=["availability"])


def csv_list(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def ensure_in_range(index, start: datetime, end: datetime) -> None:
    if not index.covers(start, end):
        raise HTTPException(status_code=422, detail=f"Dates must be between {index.start} and {index.end}")


@router.get("/search")
def search(
    session: SessionDep, user: CurrentUser, start: datetime, end: datetime, attendees: int = 0, types: str | None = None, features: str | None = None,
    optional: str | None = None, near_venue_id: int | None = None, building_id: int | None = None, dept: str | None = None, accessible: bool = False, repeat_weeks: int = 1,
) -> dict:
    index = get_index(session)
    repeat = max(1, min(repeat_weeks, 26))
    windows = [(start + timedelta(weeks=n), end + timedelta(weeks=n)) for n in range(repeat)]
    for window in windows:
        ensure_in_range(index, *window)
    request = SearchRequest(
        windows=windows, attendees=attendees, types=csv_list(types) or ["classroom", "seminar_hall"], required_features=tuple(csv_list(features)),
        optional_features=tuple(csv_list(optional)), near_venue_id=near_venue_id, building_id=building_id, dept=dept, accessible=accessible,
    )
    outcome = search_free_rooms(index, request, load_rules())
    redact = user.role != "admin"
    return {
        "windows": [[a.isoformat(), b.isoformat()] for a, b in windows], "hits": [explain.hit_card(h) for h in outcome.hits],
        "why_not": explain.why_not(outcome, redact), "considered": len(outcome.hits) + len(outcome.rejected),
    }


@router.get("/venue/{venue_id}")
def venue_timeline(venue_id: int, session: SessionDep, user: CurrentUser, date_from: date, days: int = 1) -> dict:
    index = get_index(session)
    if venue_id not in index.venue_pos:
        raise HTTPException(status_code=404, detail="Venue not found")
    venue = index.snapshot.venue(venue_id)
    redact = user.role != "admin"
    out = []
    for offset in range(max(1, min(days, 14))):
        day = date_from + timedelta(days=offset)
        if index.offset(day) is None:
            continue
        segments = []
        for segment in index.day_segments(venue_id, day):
            item = segment.as_dict()
            if redact:
                item["label"] = "Busy"
                item["source_id"] = None
            segments.append(item)
        released = [int(i) for i in index.layers[index.venue_pos[venue_id], index.offset(day), 4].nonzero()[0]]
        out.append({"date": day.isoformat(), "holiday": day in index.snapshot.holidays, "segments": segments, "released_slots": released, "free_windows": index.free_windows(venue_id, day, 30)})
    return {"venue": {"id": venue.id, "code": venue.code, "type": venue.type, "capacity": venue.capacity, "setup_buffer_min": venue.setup_buffer_min, "teardown_buffer_min": venue.teardown_buffer_min}, "days": out}


@router.get("/explain")
def explain_window(venue_id: int, start: datetime, end: datetime, session: SessionDep, user: CurrentUser) -> dict:
    index = get_index(session)
    ensure_in_range(index, start, end)
    return explain.explain_window(index, venue_id, start, end, redact=user.role != "admin")


@router.get("/heatmap")
def heatmap(session: SessionDep, user: CurrentUser, start: date, end: date, type: str = "classroom") -> dict:
    types = ("classroom", "seminar_hall") if type == "classroom" else (type,)
    return free_room_heatmap(get_index(session), load_rules(), start, end, types)


@router.post("/cohort-slots")
def cohort_slots(payload: CohortIn, session: SessionDep, user: CurrentUser) -> dict:
    sections = list(payload.section_ids)
    if not sections:
        query = select(t.Section)
        if payload.dept:
            query = query.where(t.Section.dept == payload.dept)
        if payload.semester:
            query = query.where(t.Section.semester == payload.semester)
        sections = [s.id for s in session.exec(query)]
    if not sections:
        raise HTTPException(status_code=422, detail="No sections match")
    request = CohortRequest(sections, payload.start_date, payload.end_date, payload.duration_min, payload.faculty_ids, payload.earliest, payload.latest)
    return find_common_slots(get_index(session), load_rules(), request)


@router.post("/alternatives")
def alternatives(payload: BookingIn, session: SessionDep, user: CurrentUser) -> dict:
    index = get_index(session)
    request = to_request(session, user, payload)
    return {"alternatives": alternatives_payload(index, load_rules(), request)}
