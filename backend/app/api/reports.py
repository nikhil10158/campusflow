from datetime import date

from fastapi import APIRouter, Response

from app.agent.narrative import generate_narrative
from app.deps import AdminUser, SessionDep
from app.engine import utilisation
from app.rules import load_rules
from app.services import exports, ops, reports
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


@router.get("/narrative")
def narrative(session: SessionDep, user: AdminUser, start: date = date(2026, 10, 19), end: date = date(2026, 11, 14)) -> dict:
    kpis = reports.monthly_kpis(session, start, end)
    return {"kpis": kpis, **generate_narrative(kpis)}


@router.get("/monthly.pdf")
def monthly_pdf(session: SessionDep, user: AdminUser, start: date = date(2026, 10, 19), end: date = date(2026, 11, 14)) -> Response:
    kpis = reports.monthly_kpis(session, start, end)
    return Response(exports.monthly_pdf(kpis, generate_narrative(kpis)), media_type="application/pdf")


@router.get("/monthly.xlsx")
def monthly_xlsx(session: SessionDep, user: AdminUser, start: date = date(2026, 10, 19), end: date = date(2026, 11, 14)) -> Response:
    kpis = reports.monthly_kpis(session, start, end)
    return Response(exports.workbook_bytes(exports.report_rows(kpis)), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
