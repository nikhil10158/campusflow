from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.deps import AdminUser, CurrentUser, SessionDep, require_roles
from app.engine import guesthouse, parking
from app.models import tables as t
from app.models.schemas import DecisionIn, DisruptionIn, GroupAllocateIn, ReleaseIn, RejectIn, ScanIn
from app.rules import load_rules
from app.services import audit, ops, passes
from app.services.bookings import booking_dict
from app.services.clock import get_now
from app.services.config import solver_settings
from app.services.errors import Forbidden
from app.services.snapshot import get_index, get_snapshot

router = APIRouter(tags=["resources"])
Staff = Annotated[t.User, Depends(require_roles("admin", "approver", "faculty"))]
Approver = Annotated[t.User, Depends(require_roles("admin", "approver"))]
Security = Annotated[t.User, Depends(require_roles("admin", "security", "approver"))]


@router.get("/guesthouse/availability")
def guesthouse_availability(session: SessionDep, user: CurrentUser, start: datetime, end: datetime, guests: int = 1, accessible: bool = False, category: str = "other") -> dict:
    snapshot = get_snapshot(session)
    rules = load_rules()
    ranked = guesthouse.best_fit(snapshot, rules, start, end, guests, category, accessible)
    return {
        "rooms": [{"id": r.id, "code": r.code, "type": r.type, "capacity": r.capacity, "accessible": r.accessible, "tariff_per_night": r.tariff_per_night, "estimate": guesthouse.tariff_estimate(r, start, end)} for r in ranked],
        "nights": max(1, (end.date() - start.date()).days),
    }


@router.get("/guesthouse/calendar")
def guesthouse_calendar(session: SessionDep, user: CurrentUser, date_from: date, days: int = 21) -> dict:
    snapshot = get_snapshot(session)
    rooms = [{"id": r.id, "code": r.code, "type": r.type} for r in snapshot.guest_rooms]
    last = date_from + timedelta(days=days)
    cells = []
    for b in snapshot.bookings:
        if b.resource_type == "guest_room" and b.status in ("CONFIRMED", "HELD") and b.start_dt.date() < last and b.end_dt.date() > date_from:
            cells.append({"booking_id": b.id, "room_id": b.resource_id, "start": b.start_dt.isoformat(), "end": b.end_dt.isoformat(), "status": b.status, "title": b.event_title if user.role in ("admin", "approver") else "Occupied"})
    for m in snapshot.maintenance:
        if m.resource_type == "guest_room" and m.start_dt.date() < last and m.end_dt.date() > date_from:
            cells.append({"booking_id": None, "room_id": m.resource_id, "start": m.start_dt.isoformat(), "end": m.end_dt.isoformat(), "status": "MAINTENANCE", "title": "Maintenance"})
    return {"rooms": rooms, "cells": cells, "from": date_from.isoformat(), "days": days}


@router.post("/guesthouse/group-allocate")
def group_allocate(payload: GroupAllocateIn, session: SessionDep, user: Staff) -> dict:
    snapshot = get_snapshot(session)
    rules = load_rules()
    rooms = guesthouse.available_rooms(snapshot, rules, payload.start, payload.end)
    guests = [guesthouse.GuestSpec(g.name, g.category, g.needs_accessible) for g in payload.guests]
    limits = solver_settings()
    smart = guesthouse.group_allocate(rooms, guests, payload.must_share, payload.must_not_share, min(limits["time_limit"], 5), limits["workers"])
    naive = guesthouse.greedy_allocate(rooms, guests, payload.must_not_share)
    by_id = {r.id: r for r in rooms}

    def describe(allocation: guesthouse.Allocation) -> dict:
        return {
            "status": allocation.status, "rooms_used": allocation.rooms_used, "tariff_per_night": allocation.tariff_total, "suite_misuse": allocation.suite_misuse,
            "assignments": [{"guest": guests[g].name, "room": by_id[r].code, "room_type": by_id[r].type} for g, r in sorted(allocation.assignments.items())], "violations": allocation.violations,
        }

    audit.append(session, user.email, "guesthouse.group_proposed", {"guests": len(guests), "rooms_used": smart.rooms_used})
    session.commit()
    return {"optimised": describe(smart), "greedy": describe(naive)}


@router.get("/guesthouse/waitlist")
def waitlist(session: SessionDep, user: Approver) -> dict:
    snapshot = get_snapshot(session)
    ordered = guesthouse.waitlist_order(snapshot.bookings)
    proposals = {p["booking_id"]: p for p in guesthouse.promotion_candidates(snapshot, load_rules())}
    return {"waitlist": [{"booking_id": b.id, "title": b.event_title, "priority_class": b.priority_class, "start": b.start_dt.isoformat(), "end": b.end_dt.isoformat(), "requested_type": b.meta.get("requested_type"), "promotion": proposals.get(b.id)} for b in ordered]}


@router.post("/guesthouse/waitlist/{booking_id}/promote")
def promote(booking_id: int, session: SessionDep, user: Approver) -> dict:
    booking = ops.promote_waitlisted(session, user, booking_id)
    return booking_dict(session, booking, user)


@router.get("/parking/availability")
def parking_availability(session: SessionDep, user: CurrentUser, start: datetime, end: datetime, cars: int = 0, bikes: int = 0, buses: int = 0, evs: int = 0, near_venue_id: int | None = None) -> dict:
    vehicles = {k: v for k, v in {"car": cars, "bike": bikes, "bus": buses, "ev": evs}.items() if v}
    if not vehicles:
        raise HTTPException(status_code=422, detail="Ask for at least one vehicle")
    snapshot = get_snapshot(session)
    plan = parking.check_parking(snapshot, load_rules(), start, end, vehicles, near_venue_id)
    return {
        "ok": plan.ok, "unmet": plan.unmet,
        "allocations": [{"lot_id": a.lot_id, "lot_name": a.lot_name, "vehicles": a.vehicles, "distance_m": a.distance_m, "shuttle": a.shuttle} for a in plan.allocations],
    }


@router.get("/parking/timeline")
def parking_timeline(session: SessionDep, user: CurrentUser, day: date, vehicle: str = "car") -> dict:
    snapshot = get_snapshot(session)
    rules = load_rules()
    start = datetime(day.year, day.month, day.day)
    lots = []
    for lot in snapshot.lots:
        if parking.raw_capacity(lot, vehicle) > 0:
            lots.append({"lot_id": lot.id, "name": lot.name, **parking.lot_timeline(snapshot, rules, lot, vehicle, start, start + timedelta(days=1))})
    return {"date": day.isoformat(), "vehicle": vehicle, "lots": lots}


@router.get("/parking/no-shows")
def no_shows(session: SessionDep, user: Security) -> list[dict]:
    return ops.no_show_proposals(session)


@router.post("/parking/no-shows/{booking_id}/release")
def release_no_show(booking_id: int, session: SessionDep, user: Security) -> dict:
    booking = ops.release_no_show(session, user, booking_id)
    return booking_dict(session, booking, user)


@router.post("/passes/scan")
def scan_pass(payload: ScanIn, session: SessionDep, user: Security) -> dict:
    outcome = passes.verify(session, payload.token, get_now(session), payload.lot_id, mark_scanned=True)
    audit.append(session, user.email, "pass.scanned", {"result": outcome["result"], "lot_id": payload.lot_id})
    session.commit()
    return outcome


@router.get("/verify/pass/{token}")
def verify_pass(token: str, session: SessionDep, lot_id: int | None = None) -> dict:
    return passes.verify(session, token, get_now(session), lot_id)


@router.get("/passes")
def my_passes(session: SessionDep, user: CurrentUser, booking_id: int) -> list[dict]:
    booking = session.get(t.Booking, booking_id)
    if booking is None or (user.role not in ("admin", "approver", "security") and booking.requester_id != user.id):
        raise Forbidden("You can only see passes for your own bookings")
    return [{"id": p.id, "type": p.type, "plate": p.plate, "token": passes.token_of(p), "valid_from": p.valid_from.isoformat(), "valid_to": p.valid_to.isoformat(), "revoked": p.revoked, "scanned_at": p.scanned_at.isoformat() if p.scanned_at else None} for p in session.exec(select(t.Pass).where(t.Pass.booking_id == booking_id))]


@router.post("/exceptions/propose-release")
def propose_release(payload: ReleaseIn, session: SessionDep, user: Staff) -> dict:
    exception = ops.propose_release(session, user, payload)
    return {"id": exception.id, "status": exception.status}


@router.get("/exceptions")
def exceptions(session: SessionDep, user: Staff) -> list[dict]:
    return ops.list_exceptions(session)


@router.post("/exceptions/{exception_id}/approve")
def approve_exception(exception_id: int, session: SessionDep, user: Approver, payload: DecisionIn | None = None) -> dict:
    exception = ops.decide_release(session, user, exception_id, True, payload.comment if payload else "")
    return {"id": exception.id, "status": exception.status}


@router.post("/exceptions/{exception_id}/reject")
def reject_exception(exception_id: int, payload: RejectIn, session: SessionDep, user: Approver) -> dict:
    exception = ops.decide_release(session, user, exception_id, False, payload.comment)
    return {"id": exception.id, "status": exception.status}


@router.post("/disruptions/assess")
def assess_disruption(payload: DisruptionIn, session: SessionDep, user: AdminUser) -> dict:
    return ops.assess_disruption(session, user, payload)


@router.post("/disruptions/{disruption_id}/submit")
def submit_disruption(disruption_id: int, session: SessionDep, user: AdminUser) -> dict:
    return ops.apply_disruption(session, user, disruption_id)
