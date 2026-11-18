from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import CurrentUser, SessionDep, require_roles
from app.models import tables as t
from app.models.schemas import RecoveryResubmitIn
from app.services import insights, recovery, trail

router = APIRouter(tags=["tracking"])
AdminUser = Annotated[t.User, Depends(require_roles("admin"))]
Requester = Annotated[t.User, Depends(require_roles("admin", "faculty", "student", "approver"))]


@router.get("/bookings/{booking_id}/recovery")
def booking_recovery(booking_id: int, session: SessionDep, user: CurrentUser) -> dict:
    return recovery.recovery_view(session, user, booking_id)


@router.post("/bookings/{booking_id}/resubmit")
def booking_resubmit(booking_id: int, payload: RecoveryResubmitIn, session: SessionDep, user: Requester) -> dict:
    return recovery.resubmit(session, user, booking_id, payload)


@router.get("/bookings/{booking_id}/trail")
def booking_trail(booking_id: int, session: SessionDep, user: CurrentUser) -> list[dict]:
    return trail.booking_trail(session, user, booking_id)


@router.get("/audit/approvals")
def approval_trail(session: SessionDep, user: AdminUser, limit: int = 100, offset: int = 0) -> dict:
    return {"items": trail.approval_trail(session, limit, offset)}


@router.get("/reports/utilization-summary")
def utilization_summary(session: SessionDep, user: AdminUser) -> dict:
    return insights.utilization_summary(session)
