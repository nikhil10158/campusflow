from datetime import datetime

from sqlmodel import Session, select

from app.db import begin_immediate, lock_resource
from app.engine.approvals import scope_matches
from app.engine.proposal import check_request
from app.models import tables as t
from app.rules import load_rules
from app.services import audit, calendar, passes
from app.services.bookings import alternatives_payload, booking_dict, request_from_booking
from app.services.clock import get_now
from app.services.errors import BadRequest, Conflict, Forbidden, NotFound
from app.services.notifications import notify
from app.services.snapshot import fresh_index, get_index

OPEN_STEP_STATES = ("PENDING", "ESCALATED")


def steps_of(session: Session, booking_id: int) -> list[t.ApprovalStep]:
    return list(session.exec(select(t.ApprovalStep).where(t.ApprovalStep.booking_id == booking_id).order_by(t.ApprovalStep.order)))


def is_actionable(session: Session, step: t.ApprovalStep) -> bool:
    if step.status not in OPEN_STEP_STATES:
        return False
    return all(other.status == "APPROVED" for other in steps_of(session, step.booking_id) if other.order < step.order)


def may_act(user: t.User, step: t.ApprovalStep) -> bool:
    if user.role == "admin":
        return True
    return user.role == "approver" and step.status == "PENDING" and scope_matches(user.scopes, step.scope)


def recheck(session: Session, booking: t.Booking, fresh: bool) -> dict:
    rules = load_rules()
    index = fresh_index(session, frozenset({booking.id})) if fresh else get_index(session)
    request = request_from_booking(session, booking)
    result = check_request(index, rules, request, skip_lead=True)
    return {"valid": result.ok, "check": result.as_dict(), "alternatives": [] if result.ok else alternatives_payload(index, rules, request)}


def inbox(session: Session, user: t.User) -> list[dict]:
    if user.role not in ("admin", "approver"):
        raise Forbidden("Only approvers and administrators have an approval inbox")
    begin_immediate(session)
    run_maintenance(session, get_now(session))
    items: list[dict] = []
    rows = session.exec(select(t.ApprovalStep).where(t.ApprovalStep.status.in_(OPEN_STEP_STATES)).order_by(t.ApprovalStep.due_at)).all()
    for step in rows:
        booking = session.get(t.Booking, step.booking_id)
        if booking is None or booking.status != "HELD" or not may_act(user, step) or not is_actionable(session, step):
            continue
        check = recheck(session, booking, fresh=False)
        items.append({
            "step_id": step.id, "scope": step.scope, "status": step.status, "order": step.order, "due_at": step.due_at.isoformat() if step.due_at else None,
            "escalated": step.status == "ESCALATED", "booking": booking_dict(session, booking, user), "still_valid": check["valid"],
            "violations": check["check"]["violations"], "conflicts": check["check"]["conflicts"], "alternatives": check["alternatives"],
        })
    session.rollback()
    return items


def confirm_booking(session: Session, booking: t.Booking, actor: str, now: datetime) -> None:
    booking.status = "CONFIRMED"
    booking.hold_expires_at = None
    session.add(booking)
    passes.issue_for_booking(session, booking)
    calendar.add_event(session, booking)
    requester = session.get(t.User, booking.requester_id)
    if requester:
        notify(session, requester, f"Booking #{booking.id} confirmed", f"{booking.event_title} is confirmed.", now, booking.id, ("email", "whatsapp"))
    audit.append(session, actor, "booking.confirmed", {"booking_id": booking.id})


def bundle_components(session: Session, bundle_id: int) -> list[t.Booking]:
    return list(session.exec(select(t.Booking).where(t.Booking.bundle_id == bundle_id).order_by(t.Booking.id)))


def fully_approved(session: Session, booking: t.Booking) -> bool:
    steps = steps_of(session, booking.id)
    return bool(steps) and all(s.status == "APPROVED" for s in steps)


def set_bundle_status(session: Session, bundle_id: int, status: str) -> None:
    bundle = session.get(t.BookingBundle, bundle_id)
    if bundle is not None:
        bundle.status = status
        session.add(bundle)


def confirm_bundle_if_ready(session: Session, bundle_id: int, actor: str, now: datetime) -> dict:
    everything = bundle_components(session, bundle_id)
    if any(c.status in ("REJECTED", "EXPIRED") for c in everything):
        return {"outcome": "waiting_partial"}
    components = [c for c in everything if c.status == "HELD"]
    if not components or not all(fully_approved(session, c) for c in components):
        return {"outcome": "waiting"}
    failures = []
    for component in components:
        check = recheck(session, component, fresh=True)
        if not check["valid"]:
            failures.append({"booking_id": component.id, "check": check["check"], "alternatives": check["alternatives"]})
    if failures:
        set_bundle_status(session, bundle_id, "PARTIAL")
        audit.append(session, actor, "bundle.partial", {"bundle_id": bundle_id, "failed": [f["booking_id"] for f in failures]})
        return {"outcome": "partial", "failures": failures}
    for component in components:
        confirm_booking(session, component, actor, now)
    set_bundle_status(session, bundle_id, "CONFIRMED")
    audit.append(session, actor, "bundle.confirmed", {"bundle_id": bundle_id, "components": [c.id for c in components]})
    return {"outcome": "confirmed"}


def decide(session: Session, user: t.User, step_id: int, approve: bool, comment: str) -> dict:
    begin_immediate(session)
    step = session.get(t.ApprovalStep, step_id)
    if step is None:
        raise NotFound(f"Approval step {step_id} does not exist")
    if not may_act(user, step):
        audit.append(session, user.email, "approval.forbidden", {"step_id": step_id, "scope": step.scope})
        session.commit()
        raise Forbidden("This approval step is outside your scope")
    booking = session.get(t.Booking, step.booking_id)
    if booking.status != "HELD":
        raise Conflict(f"Booking is {booking.status}, not awaiting approval")
    if not is_actionable(session, step):
        raise Conflict("An earlier approval step is still open")
    now = get_now(session)
    lock_resource(session, {"venue": "venue", "guest_room": "guest_room", "parking": "parking"}[booking.resource_type], booking.resource_id)
    if not approve:
        if not comment.strip():
            raise BadRequest("A written reason is required to reject")
        step.status, step.approver_id, step.comment, step.decided_at = "REJECTED", user.id, comment, now
        booking.status = "REJECTED"
        session.add(step)
        session.add(booking)
        if booking.bundle_id:
            set_bundle_status(session, booking.bundle_id, "PARTIAL" if any(c.status != "REJECTED" for c in bundle_components(session, booking.bundle_id)) else "REJECTED")
        requester = session.get(t.User, booking.requester_id)
        if requester:
            notify(session, requester, f"Booking #{booking.id} rejected", f"Reason: {comment}", now, booking.id, ("email", "whatsapp"))
        audit.append(session, user.email, "approval.rejected", {"step_id": step.id, "booking_id": booking.id, "reason": comment})
        session.commit()
        return {"outcome": "rejected", "booking_id": booking.id}
    check = recheck(session, booking, fresh=True)
    if not check["valid"]:
        audit.append(session, user.email, "approval.stale", {"step_id": step.id, "booking_id": booking.id, "conflicts": check["check"]["conflicts"]})
        session.commit()
        raise Conflict("Stale: the booking no longer fits, re-run alternatives", {"check": check["check"], "alternatives": check["alternatives"]})
    step.status, step.approver_id, step.comment, step.decided_at = "APPROVED", user.id, comment, now
    session.add(step)
    session.flush()
    audit.append(session, user.email, "approval.approved", {"step_id": step.id, "booking_id": booking.id, "scope": step.scope})
    outcome: dict = {"outcome": "step_approved", "booking_id": booking.id}
    requester = session.get(t.User, booking.requester_id)
    if requester and not fully_approved(session, booking):
        notify(session, requester, f"Booking #{booking.id} updated", f"The {step.scope} step approved it. It is waiting for the next approval.", now, booking.id)
    if fully_approved(session, booking):
        if booking.bundle_id:
            outcome = {**confirm_bundle_if_ready(session, booking.bundle_id, user.email, now), "booking_id": booking.id}
        else:
            confirm_booking(session, booking, user.email, now)
            outcome = {"outcome": "confirmed", "booking_id": booking.id}
    session.commit()
    return outcome


def escalate_overdue(session: Session, now: datetime) -> int:
    escalated = 0
    admins = session.exec(select(t.User).where(t.User.role == "admin")).all()
    for step in session.exec(select(t.ApprovalStep).where(t.ApprovalStep.status == "PENDING")):
        booking = session.get(t.Booking, step.booking_id)
        if booking and booking.status == "HELD" and step.due_at and step.due_at < now and is_actionable(session, step):
            step.status = "ESCALATED"
            session.add(step)
            for admin in admins:
                notify(session, admin, f"Escalated approval for booking #{booking.id}", f"Step {step.scope} was idle past its due time.", now, booking.id)
            audit.append(session, "system", "approval.escalated", {"step_id": step.id, "booking_id": booking.id})
            escalated += 1
    return escalated


def expire_holds(session: Session, now: datetime) -> int:
    expired = 0
    for booking in session.exec(select(t.Booking).where(t.Booking.status == "HELD")):
        if booking.hold_expires_at and booking.hold_expires_at < now:
            booking.status = "EXPIRED"
            session.add(booking)
            requester = session.get(t.User, booking.requester_id)
            if requester:
                notify(session, requester, f"Hold #{booking.id} expired", "The hold ran out before all approvals arrived.", now, booking.id)
            audit.append(session, "system", "booking.expired", {"booking_id": booking.id})
            expired += 1
            if booking.bundle_id:
                set_bundle_status(session, booking.bundle_id, "PARTIAL")
    return expired


def run_maintenance(session: Session, now: datetime) -> dict:
    result = {"expired": expire_holds(session, now), "escalated": escalate_overdue(session, now)}
    if result["expired"] or result["escalated"]:
        session.commit()
    return result
