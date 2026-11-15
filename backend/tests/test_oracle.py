import random
from datetime import date, datetime, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.engine import oracle
from app.engine.availability import AvailabilityIndex
from app.engine.search import SearchRequest, search_free_rooms
from app.engine.types import BookingInfo, EntryInfo, ExceptionInfo, MaintenanceInfo, Snapshot, VenueInfo
from app.rules import load_rules
from app.services import snapshot as snapshot_service

BASE = date(2026, 11, 2)
ALL_TYPES = ["classroom", "seminar_hall", "lab", "amphitheatre"]


def search_states(index: AvailabilityIndex, windows: list[tuple[datetime, datetime]]) -> dict[int, str]:
    outcome = search_free_rooms(index, SearchRequest(windows=windows, types=ALL_TYPES), load_rules())
    return {hit.venue.id: hit.state for hit in outcome.hits}


def test_search_matches_oracle_on_seeded_campus(readonly_session) -> None:
    index = snapshot_service.get_index(readonly_session)
    snapshot = index.snapshot
    generator = random.Random(7)
    venue_ids = [v.id for v in snapshot.venues]
    for _ in range(500):
        day = date(2026, 11, 16) + timedelta(days=generator.randrange(0, 28))
        start = datetime(day.year, day.month, day.day) + timedelta(minutes=5 * generator.randrange(84, 253))
        end = start + timedelta(minutes=5 * generator.randrange(3, 49))
        windows = [(start, end)]
        if generator.random() < 0.3:
            windows.append((start + timedelta(days=7), end + timedelta(days=7)))
        assert search_states(index, windows) == oracle.free_states(snapshot, windows, venue_ids), (start, end)


def test_search_is_fast_for_all_venues_over_a_week(readonly_session) -> None:
    import time

    index = snapshot_service.get_index(readonly_session)
    samples: list[float] = []
    generator = random.Random(3)
    for _ in range(60):
        day = date(2026, 11, 16) + timedelta(days=generator.randrange(0, 6))
        windows = [(datetime(day.year, day.month, day.day, 10), datetime(day.year, day.month, day.day, 11))]
        windows += [(a + timedelta(days=n), b + timedelta(days=n)) for a, b in windows for n in range(1, 7) if (a + timedelta(days=n)).date() <= date(2026, 12, 4)]
        began = time.perf_counter()
        search_free_rooms(index, SearchRequest(windows=windows, types=ALL_TYPES), load_rules())
        samples.append((time.perf_counter() - began) * 1000)
    samples.sort()
    assert samples[int(len(samples) * 0.95)] < 50


@st.composite
def small_snapshots(draw) -> Snapshot:
    now = datetime(2026, 11, 2, 8, 0)
    venues = [
        VenueInfo(
            id=number, code=f"V{number}", name="v", type="classroom", building_id=1, floor=0, capacity=50, features=(), lab_type=None,
            eligible_depts=(), needs_supervisor=False, accessible=True, bookable=draw(st.sampled_from([True, True, True, False])),
            setup_buffer_min=draw(st.sampled_from([0, 15, 30])), teardown_buffer_min=draw(st.sampled_from([0, 15, 30])), approver_scope="admin_office",
        )
        for number in range(1, 4)
    ]
    entries = [
        EntryInfo(
            id=number, section_id=1, course_code=f"C{number}", course_name="c", faculty_id=None, venue_id=draw(st.integers(1, 3)),
            weekday=draw(st.integers(0, 5)), start_min=(start := draw(st.integers(108, 200)) * 5), end_min=start + draw(st.integers(6, 36)) * 5, kind="lecture",
            effective_from=BASE + timedelta(days=draw(st.integers(0, 6))), effective_to=BASE + timedelta(days=draw(st.integers(7, 20))),
        )
        for number in range(1, draw(st.integers(0, 10)) + 1)
    ]
    exceptions: list[ExceptionInfo] = []
    if entries:
        for number in range(1, draw(st.integers(0, 6)) + 1):
            kind = draw(st.sampled_from(["cancelled", "released", "moved", "extra"]))
            exceptions.append(ExceptionInfo(
                id=number, entry_id=draw(st.sampled_from(entries)).id, date=BASE + timedelta(days=draw(st.integers(0, 13))), type=kind,
                status=draw(st.sampled_from(["APPROVED", "APPROVED", "PROPOSED", "REJECTED"])), venue_id=draw(st.integers(1, 3)),
                start_min=(first := draw(st.integers(108, 200)) * 5), end_min=first + draw(st.integers(6, 24)) * 5,
            ))
    bookings = []
    for number in range(1, draw(st.integers(0, 8)) + 1):
        start = datetime(2026, 11, 2) + timedelta(days=draw(st.integers(0, 13)), minutes=draw(st.integers(84, 252)) * 5)
        bookings.append(BookingInfo(
            id=number, bundle_id=None, resource_type="venue", resource_id=draw(st.integers(1, 3)), qty=1, requester_id=1, event_title="e", attendees=10,
            start_dt=start, end_dt=start + timedelta(minutes=draw(st.integers(1, 60)) * 5), priority_class=4,
            status=draw(st.sampled_from(["CONFIRMED", "HELD", "HELD", "CANCELLED", "EXPIRED", "REJECTED"])),
            hold_expires_at=now + timedelta(hours=draw(st.integers(-48, 48))), meta={},
        ))
    maintenance = []
    for number in range(1, draw(st.integers(0, 2)) + 1):
        start = datetime(2026, 11, 2) + timedelta(days=draw(st.integers(0, 13)), minutes=draw(st.integers(84, 252)) * 5)
        maintenance.append(MaintenanceInfo(id=number, resource_type="venue", resource_id=draw(st.integers(1, 3)), start_dt=start, end_dt=start + timedelta(minutes=draw(st.integers(1, 200)) * 5), reason="fix"))
    holidays = {BASE + timedelta(days=draw(st.integers(0, 13))) for _ in range(draw(st.integers(0, 2)))}
    return Snapshot(now=now, venues=venues, entries=entries, exceptions=exceptions, bookings=bookings, maintenance=maintenance, holidays=holidays)


@settings(max_examples=600, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(snapshot=small_snapshots(), day=st.integers(0, 13), start_slot=st.integers(80, 252), length=st.integers(1, 60), second_day=st.one_of(st.none(), st.integers(0, 13)))
def test_random_worlds_match_oracle(snapshot: Snapshot, day: int, start_slot: int, length: int, second_day: int | None) -> None:
    index = AvailabilityIndex(snapshot, BASE - timedelta(days=1), BASE + timedelta(days=30))
    start = datetime(2026, 11, 2) + timedelta(days=day, minutes=start_slot * 5)
    windows = [(start, start + timedelta(minutes=length * 5))]
    if second_day is not None:
        other = datetime(2026, 11, 2) + timedelta(days=second_day, minutes=start_slot * 5)
        windows.append((other, other + timedelta(minutes=length * 5)))
    assert search_states(index, windows) == oracle.free_states(snapshot, windows, [v.id for v in snapshot.venues])
