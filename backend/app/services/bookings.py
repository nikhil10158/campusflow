from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.db import lock_resource
from app.engine.alternatives import Alternative, recommend_alternatives
from app.engine.approvals import approval_chain
from app.engine.bundles import link_components, plan_bundle
from app.engine.proposal import CheckResult, check_request
from app.engine.types import BookingRequest
from app.models import tables as t
from app.models.schemas import BookingIn, BundleIn
from app.rules import Rules, load_rules
from app.services import audit
from app.services.clock import get_now
from app.services.errors import BadRequest, Conflict, Forbidden, NotFound
from app.services.notifications import notify
from app.services.snapshot import fresh_index, get_index

RESOURCE_TABLES = {"venue": t.Venue, "guest_room": t.GuestRoom, "parking": t.ParkingLot}


def ensure_resource(session: Session, resource_type: str, resource_id: int) -> None:
    if session.get(RESOURCE_TABLES[resource_type], resource_id) is None:
        raise NotFound(f"{resource_type} {resource_id} does not exist")


def to_request(session: Session, user: t.User, payload: BookingIn) -> BookingRequest:
    ensure_resource(session, payload.resource_type, payload.resource_id)
    if payload.end <= payload.start:
        raise BadRequest("End time must be after the start time")
    meta = dict(payload.meta)
    return BookingRequest(
        resource_type=payload.resource_type, resource_id=payload.resource_id, start=payload.start, end=payload.end, attendees=payload.attendees,
        qty=payload.qty, title=payload.event_title, purpose=payload.purpose, requester_role=user.role, requester_id=user.id,
        requester_dept=user.dept, sponsor_id=payload.sponsor_id, host_ref=payload.host_ref, features=tuple(payload.features), meta=meta,
    )


def request_from_booking(session: Session, booking: t.Booking) -> BookingRequest:
    requester = session.get(t.User, booking.requester_id)
    meta = dict(booking.meta_json)
    meta["exclude_booking_id"] = booking.id
    return BookingRequest(
        resource_type=booking.resource_type, resource_id=booking.resource_id, start=booking.start_dt, end=booking.end_dt, attendees=booking.attendees,
        qty=booking.qty, title=booking.event_title, purpose=booking.purpose, requester_role=requester.role if requester else "faculty",
        requester_id=booking.requester_id, requester_dept=requester.dept if requester else None, sponsor_id=booking.sponsor_id,
        host_ref=meta.get("host"), meta=meta,
    )


def alternatives_payload(index, rules: Rules, request: BookingRequest) -> list[dict]:
    options: list[Alternative] = recommend_alternatives(index, rules, request)
    return [o.as_dict(index.snapshot) for o in options]


def conflict_error(index, rules: Rules, result: CheckResult, message: str) -> Conflict:
    return Conflict(message, {"check": result.as_dict(), "alternatives": alternatives_payload(index, rules, result.request)})


def priority_for(rules: Rules, request: BookingRequest) -> int:
    category = request.meta.get("category")
    return rules.priority_classes.get(category, rules.priority_classes["other"]) if category else rules.priority_classes["other"]


def create_held(session: Session, rules: Rules, index, request: BookingRequest, user: t.User, now: datetime, bundle_id: int | None = None, event_title: str | None = None) -> t.Booking:
    chain = approval_chain(request, index.snapshot, rules)
    meta = {k: v for k, v in request.meta.items() if k != "exclude_booking_id"}
    meta["requester_dept"] = request.requester_dept
    booking = t.Booking(
        bundle_id=bundle_id, resource_type=request.resource_type, resource_id=request.resource_id, qty=request.qty, requester_id=user.id,
        sponsor_id=request.sponsor_id, event_title=event_title or request.title, purpose=request.purpose, attendees=request.attendees,
        start_dt=request.start, end_dt=request.end, priority_class=priority_for(rules, request), status="HELD",
        hold_expires_at=now + timedelta(hours=rules.hold_ttl_hours), created_at=now, meta_json=meta,
    )
    session.add(booking)
    session.flush()
    for order, scope in enumerate(chain, start=1):
        session.add(t.ApprovalStep(booking_id=booking.id, order=order, scope=scope, status="PENDING", due_at=now + timedelta(hours=rules.escalation_after_hours)))
    session.flush()
    return booking


def check_proposal(session: Session, user: t.User, payload: BookingIn) -> dict:
    rules = load_rules()
    index = get_index(session)
    request = to_request(session, user, payload)
    result = check_request(index, rules, request)
    body = result.as_dict()
    body["alternatives"] = [] if result.ok else alternatives_payload(index, rules, request)
    return body


def submit_booking(session: Session, user: t.User, payload: BookingIn) -> t.Booking:
    rules = load_rules()
    request = to_request(session, user, payload)
    lock_resource(session, request.resource_type, request.resource_id)
    index = fresh_index(session)
    now = get_now(session)
    result = check_request(index, rules, request)
    if not result.ok:
        audit.append(session, user.email, "booking.rejected_at_submit", {"request": payload.model_dump(mode="json"), "check": result.as_dict()})
        session.commit()
        raise conflict_error(index, rules, result, "The request cannot be held as submitted")
    booking = create_held(session, rules, index, request, user, now)
    audit.append(session, user.email, "booking.submitted", {"booking_id": booking.id, "resource": [booking.resource_type, booking.resource_id], "chain": result.approval_chain})
    notify(session, user, f"Request #{booking.id} submitted", f"{booking.event_title} is on hold until approved.", now, booking.id)
    session.commit()
    session.refresh(booking)
    return booking


def components_overlap(requests: list[BookingRequest]) -> str | None:
    for position, first in enumerate(requests):
        for second in requests[position + 1:]:
            if (first.resource_type, first.resource_id) == (second.resource_type, second.resource_id) and first.resource_type != "parking":
                if first.start < second.end and second.start < first.end:
                    return f"Two components use the same {first.resource_type} {first.resource_id} at overlapping times"
    return None


def submit_bundle(session: Session, user: t.User, payload: BundleIn) -> t.BookingBundle:
    rules = load_rules()
    requests = [to_request(session, user, component) for component in payload.components]
    for request in requests:
        lock_resource(session, request.resource_type, request.resource_id)
    index = fresh_index(session)
    now = get_now(session)
    proposal = plan_bundle(index, rules, payload.title, requests, payload.external_speakers, payload.recording)
    duplicate = components_overlap(requests)
    if not proposal.ok or duplicate:
        body = proposal.as_dict(index)
        if duplicate:
            body["bundle_violations"].append({"code": "P-BUNDLE-WINDOW", "rule_id": "BP-7.4", "severity": "hard", "message": duplicate, "fixable_by": "requester"})
        audit.append(session, user.email, "bundle.rejected_at_submit", {"title": payload.title, "proposal": body})
        session.commit()
        raise Conflict("The bundle cannot be held atomically", {"proposal": body, "alternatives": body["alternatives"]})
    bundle = t.BookingBundle(title=payload.title, requester_id=user.id, status="SUBMITTED", created_at=now)
    session.add(bundle)
    session.flush()
    for request in link_components(requests, payload.title):
        create_held(session, rules, index, request, user, now, bundle_id=bundle.id, event_title=f"{payload.title}: {request.title}" if request.title else payload.title)
    audit.append(session, user.email, "bundle.submitted", {"bundle_id": bundle.id, "components": len(requests)})
    notify(session, user, f"Bundle #{bundle.id} submitted", f"{payload.title}: {len(requests)} components are on hold together.", now, channels=("email", "whatsapp"))
    session.commit()
    session.refresh(bundle)
    return bundle


def visible_to(user: t.User, booking: t.Booking) -> bool:
    return user.role == "admin" or booking.requester_id == user.id or booking.sponsor_id == user.id


def booking_dict(session: Session, booking: t.Booking, user: t.User) -> dict:
    full = visible_to(user, booking) or user.role in ("approver", "security")
    steps = session.exec(select(t.ApprovalStep).where(t.ApprovalStep.booking_id == booking.id).order_by(t.ApprovalStep.order)).all()
    return {
        "id": booking.id, "bundle_id": booking.bundle_id, "resource_type": booking.resource_type, "resource_id": booking.resource_id,
        "start": booking.start_dt.isoformat(), "end": booking.end_dt.isoformat(), "status": booking.status,
        "event_title": booking.event_title if full else "Busy", "purpose": booking.purpose if full else "", "attendees": booking.attendees if full else None,
        "qty": booking.qty, "requester_id": booking.requester_id if full else None, "hold_expires_at": booking.hold_expires_at.isoformat() if booking.hold_expires_at else None,
        "meta": booking.meta_json if full else {}, "priority_class": booking.priority_class,
        "steps": [{"id": s.id, "order": s.order, "scope": s.scope, "status": s.status, "comment": s.comment, "decided_at": s.decided_at.isoformat() if s.decided_at else None} for s in steps] if full else [],
    }


def list_bookings(session: Session, user: t.User, status: str | None = None) -> list[dict]:
    query = select(t.Booking).order_by(t.Booking.start_dt)
    if status:
        query = query.where(t.Booking.status == status)
    rows = session.exec(query).all()
    if user.role == "student":
        rows = [b for b in rows if visible_to(user, b)]
    return [booking_dict(session, b, user) for b in rows]


def get_booking(session: Session, booking_id: int) -> t.Booking:
    booking = session.get(t.Booking, booking_id)
    if booking is None:
        raise NotFound(f"Booking {booking_id} does not exist")
    return booking


def require_owner(user: t.User, booking: t.Booking) -> None:
    if user.role != "admin" and booking.requester_id != user.id:
        raise Forbidden("Only the requester or an administrator may change this booking")
