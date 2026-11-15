from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import CurrentUser, SessionDep, require_roles
from app.models import tables as t
from app.models.schemas import BookingIn, BundleIn, DecisionIn, RejectIn, ReplaceComponentIn
from app.services import approvals, bookings, bundle_ops
from app.services.errors import Forbidden

router = APIRouter(tags=["bookings"])
Requester = Annotated[t.User, Depends(require_roles("admin", "faculty", "student", "approver"))]
Approver = Annotated[t.User, Depends(require_roles("admin", "approver"))]


@router.post("/proposals/check")
def proposal_check(payload: BookingIn, session: SessionDep, user: Requester) -> dict:
    return bookings.check_proposal(session, user, payload)


@router.post("/bookings")
def submit_booking(payload: BookingIn, session: SessionDep, user: Requester) -> dict:
    booking = bookings.submit_booking(session, user, payload)
    return bookings.booking_dict(session, booking, user)


@router.get("/bookings")
def list_bookings(session: SessionDep, user: CurrentUser, status: str | None = None) -> list[dict]:
    return bookings.list_bookings(session, user, status)


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: int, session: SessionDep, user: CurrentUser) -> dict:
    booking = bookings.get_booking(session, booking_id)
    if user.role == "student" and not bookings.visible_to(user, booking):
        raise Forbidden("Students can see only their own bookings")
    return bookings.booking_dict(session, booking, user)


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int, session: SessionDep, user: Requester) -> dict:
    return bundle_ops.cancel_booking(session, user, booking_id)


@router.post("/bundles")
def submit_bundle(payload: BundleIn, session: SessionDep, user: Requester) -> dict:
    bundle = bookings.submit_bundle(session, user, payload)
    return bundle_ops.bundle_detail(session, user, bundle.id)


@router.get("/bundles/{bundle_id}")
def get_bundle(bundle_id: int, session: SessionDep, user: CurrentUser) -> dict:
    return bundle_ops.bundle_detail(session, user, bundle_id)


@router.post("/bundles/{bundle_id}/cancel")
def cancel_bundle(bundle_id: int, session: SessionDep, user: Requester) -> dict:
    return bundle_ops.cancel_bundle(session, user, bundle_id)


@router.post("/bundles/{bundle_id}/accept-partial")
def accept_partial(bundle_id: int, session: SessionDep, user: Requester) -> dict:
    return bundle_ops.accept_partial(session, user, bundle_id)


@router.post("/bundles/{bundle_id}/replace-component")
def replace_component(bundle_id: int, payload: ReplaceComponentIn, session: SessionDep, user: Requester) -> dict:
    return bundle_ops.replace_component(session, user, bundle_id, payload.booking_id, payload.replacement)


@router.get("/approvals")
def inbox(session: SessionDep, user: Approver) -> list[dict]:
    return approvals.inbox(session, user)


@router.post("/approvals/{step_id}/approve")
def approve(step_id: int, session: SessionDep, user: Approver, payload: DecisionIn | None = None) -> dict:
    return approvals.decide(session, user, step_id, True, payload.comment if payload else "")


@router.post("/approvals/{step_id}/reject")
def reject(step_id: int, payload: RejectIn, session: SessionDep, user: Approver) -> dict:
    return approvals.decide(session, user, step_id, False, payload.comment)
