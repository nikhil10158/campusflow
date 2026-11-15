from datetime import date

from sqlmodel import Session, select

from app.engine import kpis
from app.models import tables as t
from app.rules import load_rules
from app.services.snapshot import get_index


def occupancy_samples(session: Session) -> dict:
    return {(s.venue_id, s.ts_hour): s.headcount for s in session.exec(select(t.OccupancySample))}


def decision_times(session: Session) -> list[tuple]:
    bookings = {b.id: b for b in session.exec(select(t.Booking))}
    pairs = []
    for step in session.exec(select(t.ApprovalStep).where(t.ApprovalStep.decided_at.is_not(None))):
        booking = bookings.get(step.booking_id)
        if booking and booking.created_at:
            pairs.append((booking.created_at, step.decided_at))
    return pairs


def monthly_kpis(session: Session, start: date, end: date) -> dict:
    index = get_index(session)
    scanned = {p.booking_id for p in session.exec(select(t.Pass).where(t.Pass.scanned_at.is_not(None)))}
    return kpis.compute_kpis(index, load_rules(), occupancy_samples(session), scanned, decision_times(session), start, end)
