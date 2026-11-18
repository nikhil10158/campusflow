import hashlib
import hmac
from datetime import datetime

from sqlmodel import Session, select

from app.config import get_settings
from app.models.tables import Booking, Pass
from app.services.mailer import resource_label

TOKEN_LENGTH = 24


def signature(pass_id: int, pass_type: str, resource_id: int, valid_from: datetime, valid_to: datetime, plate: str | None) -> str:
    payload = f"{pass_id}|{pass_type}|{resource_id}|{valid_from.isoformat()}|{valid_to.isoformat()}|{plate or ''}"
    return hmac.new(get_settings().pass_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def token_of(issued: Pass) -> str:
    return f"{issued.id}.{issued.token_hmac[:TOKEN_LENGTH]}"


def create_pass(session: Session, booking: Booking, pass_type: str, plate: str | None = None) -> Pass:
    issued = Pass(booking_id=booking.id, type=pass_type, resource_id=booking.resource_id, token_hmac="pending", plate=plate, valid_from=booking.start_dt, valid_to=booking.end_dt)
    session.add(issued)
    session.flush()
    issued.token_hmac = signature(issued.id, pass_type, issued.resource_id, issued.valid_from, issued.valid_to, plate)
    session.add(issued)
    session.flush()
    return issued


def issue_for_booking(session: Session, booking: Booking) -> list[Pass]:
    if booking.resource_type == "parking":
        plates = booking.meta_json.get("plates") or [f"SYN {booking.id:03d} {n:02d}" for n in range(booking.qty)]
        return [create_pass(session, booking, "parking", plate) for plate in plates]
    if booking.resource_type == "guest_room":
        return [create_pass(session, booking, "guesthouse")]
    return [create_pass(session, booking, "venue")]


def revoke_for_booking(session: Session, booking_id: int) -> int:
    revoked = 0
    for issued in session.exec(select(Pass).where(Pass.booking_id == booking_id)):
        if not issued.revoked:
            issued.revoked = True
            session.add(issued)
            revoked += 1
    return revoked


def lookup(session: Session, token: str) -> Pass | None:
    pass_id, _, prefix = token.partition(".")
    if not pass_id.isdigit() or not prefix:
        return None
    issued = session.get(Pass, int(pass_id))
    if issued is None:
        return None
    expected = signature(issued.id, issued.type, issued.resource_id, issued.valid_from, issued.valid_to, issued.plate)
    if not hmac.compare_digest(expected, issued.token_hmac) or not hmac.compare_digest(expected[:TOKEN_LENGTH], prefix):
        return None
    return issued


def verify(session: Session, token: str, now: datetime, lot_id: int | None = None, mark_scanned: bool = False) -> dict:
    issued = lookup(session, token)
    if issued is None:
        return {"result": "NOT_FOUND", "pass": None}
    details = {"id": issued.id, "type": issued.type, "plate": issued.plate, "resource_id": issued.resource_id, "valid_from": issued.valid_from.isoformat(), "valid_to": issued.valid_to.isoformat(), "scanned_at": issued.scanned_at.isoformat() if issued.scanned_at else None}
    booking = session.get(Booking, issued.booking_id)
    if booking is not None:
        details["booking"] = {"id": booking.id, "title": booking.event_title, "resource": resource_label(session, booking), "status": booking.status}
    if issued.revoked or booking is None or booking.status not in ("CONFIRMED", "COMPLETED"):
        return {"result": "REVOKED", "pass": details}
    if now > issued.valid_to:
        return {"result": "EXPIRED", "pass": details}
    if now < issued.valid_from:
        return {"result": "NOT_YET_VALID", "pass": details}
    if lot_id is not None and issued.type == "parking" and issued.resource_id != lot_id:
        return {"result": "WRONG_LOT", "pass": details}
    if mark_scanned:
        issued.scanned_at = now
        session.add(issued)
        details["scanned_at"] = now.isoformat()
    return {"result": "VALID", "pass": details}
