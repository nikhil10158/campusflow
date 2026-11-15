from datetime import date

from fastapi import APIRouter, HTTPException, Response

from app.deps import AdminUser, CurrentUser, SessionDep
from app.models import tables as t
from app.services import audit, exports
from app.services.bookings import get_booking, visible_to

router = APIRouter(prefix="/exports", tags=["exports"])
PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def log_export(session: SessionDep, user: t.User, what: str) -> None:
    audit.append(session, user.email, "export.created", {"what": what})
    session.commit()


@router.get("/venue/{venue_id}.pdf")
def venue_schedule(venue_id: int, session: SessionDep, user: CurrentUser, date_from: date, days: int = 7) -> Response:
    data = exports.venue_schedule_pdf(session, venue_id, date_from, max(1, min(days, 31)), redact=user.role != "admin")
    log_export(session, user, f"venue {venue_id} schedule")
    return Response(data, media_type=PDF)


@router.get("/bookings/{booking_id}.pdf")
def booking_confirmation(booking_id: int, session: SessionDep, user: CurrentUser) -> Response:
    booking = get_booking(session, booking_id)
    if not visible_to(user, booking) and user.role not in ("approver",):
        raise HTTPException(status_code=403, detail="Only the requester or an administrator can download this")
    data = exports.booking_pdf(session, booking)
    log_export(session, user, f"booking {booking_id} confirmation")
    return Response(data, media_type=PDF)


@router.get("/passes/{pass_id}.pdf")
def pass_document(pass_id: int, session: SessionDep, user: CurrentUser) -> Response:
    issued = session.get(t.Pass, pass_id)
    if issued is None:
        raise HTTPException(status_code=404, detail="Pass not found")
    booking = session.get(t.Booking, issued.booking_id)
    if user.role not in ("admin", "approver", "security") and booking.requester_id != user.id:
        raise HTTPException(status_code=403, detail="You can only download your own passes")
    return Response(exports.pass_pdf(session, issued), media_type=PDF)


@router.get("/guesthouse/checkin.pdf")
def checkin_sheet(session: SessionDep, user: CurrentUser, day: date) -> Response:
    if user.role not in ("admin", "approver"):
        raise HTTPException(status_code=403, detail="Only the guest house manager or an administrator can print this")
    data = exports.checkin_sheet_pdf(session, day)
    log_export(session, user, "guest check-in sheet")
    return Response(data, media_type=PDF)


@router.get("/{name}.xlsx")
def spreadsheet(name: str, session: SessionDep, user: AdminUser) -> Response:
    builders = {"bookings": exports.bookings_rows, "guesthouse": exports.guesthouse_rows, "parking": exports.parking_rows, "audit": exports.audit_rows}
    if name not in builders:
        raise HTTPException(status_code=404, detail="Unknown export")
    data = exports.workbook_bytes({name.title(): builders[name](session)})
    log_export(session, user, f"{name} spreadsheet")
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
