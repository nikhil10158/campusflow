from sqlmodel import Session

from app.engine import guesthouse
from app.models import tables as t
from app.models.schemas import BookingIn
from app.rules import load_rules
from app.services import audit, calendar, passes
from app.services.approvals import bundle_components, confirm_booking, fully_approved, recheck, set_bundle_status, steps_of
from app.services.bookings import booking_dict, create_held, get_booking, require_owner, to_request
from app.services.clock import get_now
from app.services.errors import BadRequest, Conflict, Forbidden, NotFound
from app.services.notifications import notify
from app.services.snapshot import fresh_index, get_snapshot


def get_bundle(session: Session, bundle_id: int) -> t.BookingBundle:
    bundle = session.get(t.BookingBundle, bundle_id)
    if bundle is None:
        raise NotFound(f"Bundle {bundle_id} does not exist")
    return bundle


def timeline_of(session: Session, bundle: t.BookingBundle, components: list[t.Booking]) -> list[dict]:
    events = [{"stage": "SUBMITTED", "at": bundle.created_at.isoformat(), "detail": f"{len(components)} components held together"}]
    for component in components:
        for step in steps_of(session, component.id):
            if step.decided_at:
                events.append({"stage": step.status, "at": step.decided_at.isoformat(), "detail": f"{component.resource_type} #{component.id}: {step.scope}"})
    events.sort(key=lambda e: e["at"])
    return events


def bundle_detail(session: Session, user: t.User, bundle_id: int) -> dict:
    bundle = get_bundle(session, bundle_id)
    if user.role not in ("admin", "approver") and bundle.requester_id != user.id:
        raise Forbidden("Only the requester, approvers and administrators can see this bundle")
    components = bundle_components(session, bundle_id)
    return {
        "id": bundle.id, "title": bundle.title, "status": bundle.status, "requester_id": bundle.requester_id,
        "components": [booking_dict(session, c, user) for c in components], "timeline": timeline_of(session, bundle, components),
    }


def release_component(session: Session, booking: t.Booking, status: str, now) -> None:
    booking.status = status
    session.add(booking)
    passes.revoke_for_booking(session, booking.id)
    calendar.remove_events(session, booking.id)


def waitlist_proposals(session: Session) -> list[dict]:
    snapshot = get_snapshot(session)
    return guesthouse.promotion_candidates(snapshot, load_rules())


def cancel_booking(session: Session, user: t.User, booking_id: int) -> dict:
    booking = get_booking(session, booking_id)
    require_owner(user, booking)
    if booking.status in ("CANCELLED", "REJECTED", "EXPIRED", "COMPLETED"):
        raise Conflict(f"Booking is already {booking.status}")
    now = get_now(session)
    release_component(session, booking, "CANCELLED", now)
    if booking.bundle_id:
        remaining = [c for c in bundle_components(session, booking.bundle_id) if c.status in ("HELD", "CONFIRMED")]
        set_bundle_status(session, booking.bundle_id, "PARTIAL" if remaining else "CANCELLED")
    audit.append(session, user.email, "booking.cancelled", {"booking_id": booking.id})
    session.flush()
    session.commit()
    promotions = waitlist_proposals(session) if booking.resource_type == "guest_room" else []
    return {"booking_id": booking.id, "status": "CANCELLED", "waitlist_promotions": promotions}


def cancel_bundle(session: Session, user: t.User, bundle_id: int) -> dict:
    bundle = get_bundle(session, bundle_id)
    if user.role != "admin" and bundle.requester_id != user.id:
        raise Forbidden("Only the requester or an administrator may cancel this bundle")
    now = get_now(session)
    cancelled = []
    for component in bundle_components(session, bundle_id):
        if component.status in ("HELD", "CONFIRMED", "WAITLISTED"):
            release_component(session, component, "CANCELLED", now)
            cancelled.append(component.id)
    bundle.status = "CANCELLED"
    session.add(bundle)
    requester = session.get(t.User, bundle.requester_id)
    if requester:
        notify(session, requester, f"Bundle #{bundle.id} cancelled", f"All {len(cancelled)} components were released.", now, channels=("email", "whatsapp"))
    audit.append(session, user.email, "bundle.cancelled", {"bundle_id": bundle_id, "released": cancelled})
    session.commit()
    return {"bundle_id": bundle_id, "status": "CANCELLED", "released": cancelled}


def accept_partial(session: Session, user: t.User, bundle_id: int) -> dict:
    bundle = get_bundle(session, bundle_id)
    if user.role != "admin" and bundle.requester_id != user.id:
        raise Forbidden("Only the requester or an administrator may accept a partial bundle")
    if bundle.status != "PARTIAL":
        raise Conflict(f"Bundle is {bundle.status}, not PARTIAL")
    now = get_now(session)
    confirmed, dropped = [], []
    for component in bundle_components(session, bundle_id):
        if component.status != "HELD":
            continue
        if fully_approved(session, component) and recheck(session, component, fresh=True)["valid"]:
            confirm_booking(session, component, user.email, now)
            confirmed.append(component.id)
        else:
            release_component(session, component, "CANCELLED", now)
            dropped.append(component.id)
    bundle.status = "CONFIRMED" if confirmed else "CANCELLED"
    session.add(bundle)
    audit.append(session, user.email, "bundle.partial_accepted", {"bundle_id": bundle_id, "confirmed": confirmed, "dropped": dropped})
    session.commit()
    return {"bundle_id": bundle_id, "status": bundle.status, "confirmed": confirmed, "dropped": dropped}


def replace_component(session: Session, user: t.User, bundle_id: int, booking_id: int, replacement: BookingIn) -> dict:
    bundle = get_bundle(session, bundle_id)
    if user.role != "admin" and bundle.requester_id != user.id:
        raise Forbidden("Only the requester or an administrator may replace a component")
    old = get_booking(session, booking_id)
    if old.bundle_id != bundle_id:
        raise BadRequest("That booking is not part of this bundle")
    from app.engine.proposal import check_request
    from app.services.bookings import conflict_error

    rules = load_rules()
    request = to_request(session, user, replacement)
    request.meta = {**request.meta, "bundle_event": bundle.title}
    request.host_ref = request.host_ref or bundle.title
    index = fresh_index(session, frozenset({old.id}))
    result = check_request(index, rules, request)
    if not result.ok:
        raise conflict_error(index, rules, result, "The replacement cannot be held")
    now = get_now(session)
    release_component(session, old, "CANCELLED", now)
    created = create_held(session, rules, index, request, user, now, bundle_id=bundle_id, event_title=f"{bundle.title}: {request.title}")
    set_bundle_status(session, bundle_id, "SUBMITTED" if not any(c.status in ("REJECTED", "EXPIRED") for c in bundle_components(session, bundle_id)) else "PARTIAL")
    audit.append(session, user.email, "bundle.component_replaced", {"bundle_id": bundle_id, "old": old.id, "new": created.id})
    session.commit()
    return {"bundle_id": bundle_id, "replaced": old.id, "new_booking_id": created.id}
