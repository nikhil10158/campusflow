from datetime import date

from fastapi import APIRouter

from app.deps import AdminUser, SessionDep
from app.engine import utilisation
from app.rules import load_rules
from app.services import ops, reports
from app.services.snapshot import get_index

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/utilisation")
def utilisation_report(session: SessionDep, user: AdminUser, start: date = date(2026, 10, 19), end: date = date(2026, 11, 14)) -> dict:
    index = get_index(session)
    rows = utilisation.venue_utilisation(index, start, end, ("classroom", "seminar_hall", "lab", "amphitheatre"))
    return {
        "venues": rows, "by_type": utilisation.group_mean(rows, "type"), "hourly": utilisation.hourly_profile(index, start, end),
        "fragmentation": utilisation.fragmentation(index, start, end), "heatmap": utilisation.free_room_heatmap(index, load_rules(), start, end),
    }


@router.get("/ghosts")
def ghosts(session: SessionDep, user: AdminUser) -> dict:
    return ops.ghost_report(session)


@router.get("/monthly")
def monthly(session: SessionDep, user: AdminUser, start: date = date(2026, 10, 19), end: date = date(2026, 11, 14)) -> dict:
    return reports.monthly_kpis(session, start, end)
