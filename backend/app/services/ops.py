from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.engine import impact, parking
from app.engine.ghost import detect_ghosts, projected_uplift_hours
from app.models import tables as t
from app.models.schemas import DisruptionIn, ReleaseIn
from app.rules import load_rules
from app.services import audit, calendar, passes
from app.services.clock import get_now
from app.services.config import solver_settings
from app.services.errors import BadRequest, Conflict, Forbidden, NotFound
from app.services.notifications import notify
from app.services.snapshot import get_index, get_snapshot


def section_dept(session: Session, entry_id: int) -> str:
    entry = session.get(t.TimetableEntry, entry_id)
    section = session.get(t.Section, entry.section_id)
    return section.dept


def propose_release(session: Session, user: t.User, payload: ReleaseIn) -> t.ScheduleException:
    entry = session.get(t.TimetableEntry, payload.entry_id)
    if entry is None:
        raise NotFound("Timetable entry not found")
    if user.role == "faculty" and entry.faculty_id != user.ref_id:
        raise Forbidden("Faculty can propose release only for their own classes")
    if user.role not in ("faculty", "admin", "approver"):
        raise Forbidden("Your role cannot propose a release")
    if payload.date.weekday() != entry.weekday:
        raise BadRequest("The date does not match the weekday of this class")
    duplicate = session.exec(select(t.ScheduleException).where(t.ScheduleException.entry_id == entry.id, t.ScheduleException.date == payload.date, t.ScheduleException.status.in_(["PROPOSED", "APPROVED"]))).first()
    if duplicate:
        raise Conflict("A release is already proposed or approved for that class and date")
    exception = t.ScheduleException(entry_id=entry.id, date=payload.date, type="released", reason=payload.reason, status="PROPOSED", created_by=user.id)
    session.add(exception)
    session.flush()
    audit.append(session, user.email, "exception.proposed", {"exception_id": exception.id, "entry_id": entry.id, "date": payload.date.isoformat()})
    session.commit()
    return exception


def decide_release(session: Session, user: t.User, exception_id: int, approve: bool, comment: str = "") -> t.ScheduleException:
    exception = session.get(t.ScheduleException, exception_id)
    if exception is None:
        raise NotFound("Exception not found")
    if exception.status != "PROPOSED":
        raise Conflict(f"Exception is already {exception.status}")
    dept = section_dept(session, exception.entry_id)
    if user.role != "admin" and f"hod:{dept}" not in user.scopes:
        audit.append(session, user.email, "exception.forbidden", {"exception_id": exception_id})
        session.commit()
        raise Forbidden("Only the head of the department or an administrator may decide a release")
    if not approve and not comment.strip():
        raise BadRequest("A written reason is required to reject")
    exception.status = "APPROVED" if approve else "REJECTED"
    session.add(exception)
    audit.append(session, user.email, "exception.approved" if approve else "exception.rejected", {"exception_id": exception.id, "reason": comment})
    session.commit()
    return exception


def list_exceptions(session: Session) -> list[dict]:
    rows = session.exec(select(t.ScheduleException).order_by(t.ScheduleException.date)).all()
    entries = {e.id: e for e in session.exec(select(t.TimetableEntry))}
    venues = {v.id: v.code for v in session.exec(select(t.Venue))}
    return [
        {"id": r.id, "entry_id": r.entry_id, "date": r.date.isoformat(), "type": r.type, "status": r.status, "reason": r.reason,
         "course_code": entries[r.entry_id].course_code, "venue_code": venues[entries[r.entry_id].venue_id],
         "start_min": entries[r.entry_id].start_min, "end_min": entries[r.entry_id].end_min}
        for r in rows
    ]


def ghost_report(session: Session) -> dict:
    snapshot = get_snapshot(session)
    samples = {(s.venue_id, s.ts_hour): s.headcount for s in session.exec(select(t.OccupancySample))}
    findings = detect_ghosts(snapshot, samples, load_rules(), snapshot.now.date())
    venues = {v.id: v for v in snapshot.venues}
    items = []
    for finding in findings:
        entry = finding.entry
        section = snapshot.sections[entry.section_id]
        sparkline = [round(o["ratio"], 2) for o in finding.occurrences]
        next_day = snapshot.now.date() + timedelta(days=(entry.weekday - snapshot.now.weekday()) % 7)
        if next_day <= snapshot.now.date():
            next_day += timedelta(days=7)
        items.append({
            "entry_id": entry.id, "course_code": entry.course_code, "section": f"{section.dept} Sem {section.semester}-{section.name}", "venue_code": venues[entry.venue_id].code,
            "weekday": entry.weekday, "start_min": entry.start_min, "end_min": entry.end_min, "section_size": finding.section_size, "mean_ratio": finding.mean_ratio,
            "low_occurrences": finding.low_count, "occurrences": finding.occurrences, "sparkline": sparkline, "weekly_hours": finding.weekly_hours, "next_date": next_day.isoformat(),
            "released_already": any(e.entry_id == entry.id and e.status in ("APPROVED", "PROPOSED") for e in snapshot.exceptions),
        })
    return {"ghosts": items, "projected_uplift_hours_per_week": projected_uplift_hours(findings), "threshold": load_rules().ghost.threshold}


def promote_waitlisted(session: Session, user: t.User, booking_id: int) -> t.Booking:
    if user.role != "admin" and "guesthouse_mgr" not in user.scopes:
        raise Forbidden("Only the guest house manager or an administrator may promote a waitlisted request")
    booking = session.get(t.Booking, booking_id)
    if booking is None or booking.status != "WAITLISTED":
        raise NotFound("No waitlisted booking with that id")
    from app.engine import guesthouse

    snapshot = get_snapshot(session)
    proposals = {p["booking_id"]: p for p in guesthouse.promotion_candidates(snapshot, load_rules())}
    proposal = proposals.get(booking_id)
    if proposal is None:
        raise Conflict("No suitable room is free for this waitlisted request yet")
    now = get_now(session)
    booking.resource_id = proposal["room_id"]
    booking.status = "HELD"
    booking.hold_expires_at = now + timedelta(hours=load_rules().hold_ttl_hours)
    session.add(booking)
    session.add(t.ApprovalStep(booking_id=booking.id, order=1, scope="guesthouse_mgr", status="PENDING", due_at=now + timedelta(hours=load_rules().escalation_after_hours)))
    audit.append(session, user.email, "waitlist.promoted", {"booking_id": booking.id, "room": proposal["room_code"]})
    session.commit()
    return booking


def no_show_proposals(session: Session) -> list[dict]:
    snapshot = get_snapshot(session)
    scanned = {p.booking_id for p in session.exec(select(t.Pass).where(t.Pass.scanned_at.is_not(None)))}
    ids = parking.no_show_candidates(snapshot, load_rules(), scanned)
    lots = {l.id: l.name for l in snapshot.lots}
    return [
        {"booking_id": b.id, "title": b.event_title, "lot": lots[b.resource_id], "start": b.start_dt.isoformat(), "end": b.end_dt.isoformat(), "vehicles": parking.vehicles_of(b.meta, b.qty)}
        for b in snapshot.bookings if b.id in ids
    ]


def release_no_show(session: Session, user: t.User, booking_id: int) -> t.Booking:
    if user.role != "admin" and "parking_officer" not in user.scopes and user.role != "security":
        raise Forbidden("Only the parking officer, security or an administrator may release a no-show")
    if booking_id not in {p["booking_id"] for p in no_show_proposals(session)}:
        raise Conflict("That booking is not a no-show candidate")
    booking = session.get(t.Booking, booking_id)
    booking.status = "NO_SHOW"
    session.add(booking)
    passes.revoke_for_booking(session, booking.id)
    calendar.remove_events(session, booking.id)
    audit.append(session, user.email, "parking.no_show_released", {"booking_id": booking.id})
    session.commit()
    return booking


def closure_from_input(session: Session, payload: DisruptionIn) -> impact.Closure:
    venue_ids = list(payload.venue_ids)
    if payload.building_id:
        venue_ids += [v.id for v in session.exec(select(t.Venue).where(t.Venue.building_id == payload.building_id))]
    if payload.kind == "venue" and not venue_ids:
        raise BadRequest("Choose at least one venue or a building")
    return impact.Closure(payload.kind, payload.start, payload.end, venue_ids, payload.faculty_id, payload.lot_id, payload.description)


def assess_disruption(session: Session, user: t.User, payload: DisruptionIn) -> dict:
    closure = closure_from_input(session, payload)
    limits = solver_settings()
    report = impact.assess(get_index(session), load_rules(), closure, limits["time_limit"], limits["workers"])
    disruption = t.Disruption(kind=payload.kind, description=payload.description, start_dt=payload.start, end_dt=payload.end, venue_ids=closure.venue_ids, plan_json=report, status="PROPOSED", created_by=user.id)
    session.add(disruption)
    session.flush()
    audit.append(session, user.email, "disruption.assessed", {"disruption_id": disruption.id, "affected": report["affected"], "resolved": report["resolved"]})
    session.commit()
    return {"disruption_id": disruption.id, **report}


def apply_disruption(session: Session, user: t.User, disruption_id: int) -> dict:
    disruption = session.get(t.Disruption, disruption_id)
    if disruption is None:
        raise NotFound("Disruption not found")
    if disruption.status != "PROPOSED":
        raise Conflict(f"Disruption is already {disruption.status}")
    now = get_now(session)
    applied = 0
    for item in disruption.plan_json.get("items", []):
        proposal = item.get("proposal")
        if not proposal:
            continue
        if item["kind"] == "class" and "venue_id" in proposal:
            session.add(t.ScheduleException(entry_id=item["source_id"], date=datetime.fromisoformat(item["start"]).date(), type="moved", reason=disruption.description, status="APPROVED", created_by=user.id, venue_id=proposal["venue_id"], start_min=datetime.fromisoformat(proposal["start"]).hour * 60 + datetime.fromisoformat(proposal["start"]).minute, end_min=datetime.fromisoformat(proposal["end"]).hour * 60 + datetime.fromisoformat(proposal["end"]).minute))
        elif item["kind"] == "class" and proposal.get("action") == "cancel":
            session.add(t.ScheduleException(entry_id=item["source_id"], date=datetime.fromisoformat(item["start"]).date(), type="cancelled", reason=disruption.description, status="APPROVED", created_by=user.id))
        elif item["kind"] == "booking" and "venue_id" in proposal:
            booking = session.get(t.Booking, item["source_id"])
            booking.resource_id = proposal["venue_id"]
            booking.start_dt = datetime.fromisoformat(proposal["start"])
            booking.end_dt = datetime.fromisoformat(proposal["end"])
            session.add(booking)
            requester = session.get(t.User, booking.requester_id)
            if requester:
                notify(session, requester, f"Booking #{booking.id} moved", proposal["what_changed"], now, booking.id, ("email", "whatsapp"))
        elif item["kind"] == "booking" and proposal.get("action") == "move_parking" and proposal["allocations"]:
            booking = session.get(t.Booking, item["source_id"])
            first = proposal["allocations"][0]
            booking.resource_id = first["lot_id"]
            booking.meta_json = {**booking.meta_json, "vehicles": first["vehicles"]}
            session.add(booking)
        applied += 1
    disruption.status = "APPLIED"
    session.add(disruption)
    audit.append(session, user.email, "disruption.applied", {"disruption_id": disruption.id, "changes": applied})
    session.commit()
    return {"disruption_id": disruption.id, "status": "APPLIED", "changes": applied}
