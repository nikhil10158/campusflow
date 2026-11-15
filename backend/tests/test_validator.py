import copy
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.engine import validator
from app.engine.types import BookingInfo, MaintenanceInfo, PassInfo, Snapshot, StepInfo
from app.rules import load_rules
from app.services import snapshot as snapshot_service

NEW_ID = 9000


@pytest.fixture(scope="module")
def base(readonly_session) -> Snapshot:
    return snapshot_service.load_snapshot(readonly_session)


def codes(snapshot: Snapshot) -> set[str]:
    return {v.code for v in validator.validate(snapshot, load_rules())}


def mutated(snapshot: Snapshot) -> Snapshot:
    clone = copy.copy(snapshot)
    clone.bookings = list(snapshot.bookings)
    clone.steps = list(snapshot.steps)
    clone.passes = list(snapshot.passes)
    clone.maintenance = list(snapshot.maintenance)
    return clone


def booking(resource_type: str, resource_id: int, start: datetime, end: datetime, **extra) -> BookingInfo:
    values = dict(id=NEW_ID + len(extra), bundle_id=None, resource_type=resource_type, resource_id=resource_id, qty=1, requester_id=1, event_title="mutation", attendees=10, start_dt=start, end_dt=end, priority_class=4, status="CONFIRMED", hold_expires_at=None, meta={})
    values.update(extra)
    return BookingInfo(**values)


def approve(clone: Snapshot, item: BookingInfo) -> None:
    clone.steps.append(StepInfo(id=NEW_ID + item.id, booking_id=item.id, order=1, scope="admin_office", status="APPROVED"))


def venue_by_code(snapshot: Snapshot, code: str):
    return next(v for v in snapshot.venues if v.code == code)


def test_baseline_state_is_valid(base: Snapshot) -> None:
    assert validator.validate(base, load_rules()) == []


def test_catches_overlapping_confirmed_bookings(base: Snapshot) -> None:
    existing = next(b for b in base.bookings if b.resource_type == "venue" and b.status == "CONFIRMED")
    clone = mutated(base)
    clone.bookings.append(booking("venue", existing.resource_id, existing.start_dt, existing.end_dt, id=NEW_ID))
    assert "H-VENUE-OVERLAP" in codes(clone)


def test_catches_booking_over_timetable_class(base: Snapshot) -> None:
    entry = next(e for e in base.entries if e.weekday == 1)
    day = datetime(2026, 11, 17)
    clone = mutated(base)
    clone.bookings.append(booking("venue", entry.venue_id, day + timedelta(minutes=entry.start_min), day + timedelta(minutes=entry.end_min), id=NEW_ID))
    assert "H-VENUE-OVERLAP" in codes(clone)


def test_catches_capacity_breach(base: Snapshot) -> None:
    amphitheatre = venue_by_code(base, "AMP-1")
    start = datetime(2026, 12, 10, 10)
    clone = mutated(base)
    item = booking("venue", amphitheatre.id, start, start + timedelta(hours=2), id=NEW_ID, attendees=amphitheatre.capacity + 1)
    clone.bookings.append(item)
    approve(clone, item)
    assert "H-VENUE-CAPACITY" in codes(clone)


def test_catches_buffer_violation(base: Snapshot) -> None:
    amphitheatre = venue_by_code(base, "AMP-1")
    start = datetime(2026, 12, 10, 10)
    clone = mutated(base)
    first = booking("venue", amphitheatre.id, start, start + timedelta(hours=2), id=NEW_ID)
    second = booking("venue", amphitheatre.id, start + timedelta(hours=2, minutes=10), start + timedelta(hours=4), id=NEW_ID + 1)
    clone.bookings += [first, second]
    approve(clone, first)
    approve(clone, second)
    assert "H-BUFFER" in codes(clone)


def test_catches_maintenance_clash(base: Snapshot) -> None:
    classroom = next(v for v in base.venues if v.type == "classroom")
    start = datetime(2026, 12, 10, 10)
    clone = mutated(base)
    clone.maintenance.append(MaintenanceInfo(id=NEW_ID, resource_type="venue", resource_id=classroom.id, start_dt=start, end_dt=start + timedelta(hours=4), reason="x"))
    item = booking("venue", classroom.id, start + timedelta(hours=1), start + timedelta(hours=2), id=NEW_ID)
    clone.bookings.append(item)
    approve(clone, item)
    assert "H-VENUE-OVERLAP" in codes(clone)


def test_catches_guest_room_double_booking(base: Snapshot) -> None:
    existing = next(b for b in base.bookings if b.resource_type == "guest_room" and b.status == "CONFIRMED")
    clone = mutated(base)
    item = booking("guest_room", existing.resource_id, existing.start_dt, existing.end_dt, id=NEW_ID)
    clone.bookings.append(item)
    approve(clone, item)
    assert "H-GUEST-OVERLAP" in codes(clone)


def test_catches_missing_turnover(base: Snapshot) -> None:
    existing = next(b for b in base.bookings if b.resource_type == "guest_room" and b.status == "CONFIRMED")
    clone = mutated(base)
    item = booking("guest_room", existing.resource_id, existing.end_dt + timedelta(minutes=10), existing.end_dt + timedelta(days=1), id=NEW_ID)
    clone.bookings.append(item)
    approve(clone, item)
    assert "H-GUEST-OVERLAP" in codes(clone)


def test_catches_parking_over_capacity(base: Snapshot) -> None:
    lot = base.lots[0]
    start = datetime(2026, 12, 10, 9)
    clone = mutated(base)
    item = booking("parking", lot.id, start, start + timedelta(hours=3), id=NEW_ID, qty=lot.cap_car, attendees=lot.cap_car, meta={"vehicles": {"car": lot.cap_car}})
    clone.bookings.append(item)
    approve(clone, item)
    assert "H-PARK-OVERCAP" in codes(clone)


def test_catches_bundle_window_gaps(base: Snapshot) -> None:
    amphitheatre = venue_by_code(base, "AMP-1")
    start = datetime(2026, 12, 11, 10)
    clone = mutated(base)
    event = booking("venue", amphitheatre.id, start, start + timedelta(hours=2), id=NEW_ID, bundle_id=77)
    stay = booking("guest_room", 1, datetime(2026, 12, 12, 14), datetime(2026, 12, 13, 11), id=NEW_ID + 1, bundle_id=77)
    clone.bookings += [event, stay]
    approve(clone, event)
    approve(clone, stay)
    assert "H-BUNDLE-WINDOW" in codes(clone)


def test_catches_confirmed_booking_without_approval(base: Snapshot) -> None:
    clone = mutated(base)
    target = next(s for s in base.steps if s.status == "APPROVED")
    clone.steps = [replace(s, status="PENDING") if s.id == target.id else s for s in base.steps]
    assert "H-APPROVAL-MISSING" in codes(clone)


def test_catches_pass_for_unconfirmed_booking(base: Snapshot) -> None:
    held = next(b for b in base.bookings if b.status == "HELD")
    clone = mutated(base)
    clone.passes.append(PassInfo(id=NEW_ID, booking_id=held.id, type="venue", resource_id=held.resource_id, plate=None, valid_from=held.start_dt, valid_to=held.end_dt, revoked=False))
    assert "H-PASS-ORPHAN" in codes(clone)


def test_catches_hard_policy_breaches(base: Snapshot) -> None:
    classroom = next(v for v in base.venues if v.type == "classroom")
    start = datetime(2026, 12, 10, 7)
    clone = mutated(base)
    long_booking = booking("venue", classroom.id, start, start + timedelta(hours=10), id=NEW_ID)
    long_stay = booking("guest_room", 3, datetime(2026, 12, 20, 14), datetime(2026, 12, 28, 11), id=NEW_ID + 1)
    clone.bookings += [long_booking, long_stay]
    approve(clone, long_booking)
    approve(clone, long_stay)
    assert "H-POLICY-HARD" in codes(clone)


def test_candidate_check_ignores_unrelated_state(base: Snapshot) -> None:
    clone = mutated(base)
    clone.steps = []
    only = {("venue", 1)}
    assert validator.validate(clone, load_rules(), only) == []
