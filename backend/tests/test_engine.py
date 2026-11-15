import re
from datetime import date, datetime, timedelta

import pytest

from app.config import DATA_DIR
from app.engine import batch, guesthouse, impact, parking, policy
from app.engine.alternatives import recommend_alternatives
from app.engine.bundles import plan_bundle
from app.engine.cohort import CohortRequest, find_common_slots
from app.engine.ghost import detect_ghosts
from app.engine.proposal import check_request
from app.engine.search import SearchRequest, search_free_rooms
from app.engine.types import BookingRequest
from app.engine.utilisation import free_room_heatmap
from app.engine import validator
from app.rules import load_rules
from app.services import snapshot as snapshot_service
from app.models import tables as t
from sqlmodel import select

RULES = load_rules()


@pytest.fixture(scope="module")
def index(readonly_session):
    return snapshot_service.get_index(readonly_session)


def at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00")


def collect_numbers(value, found: list) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            collect_numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            collect_numbers(item, found)


def test_every_number_in_rules_appears_in_policies() -> None:
    import yaml
    from app.rules import RULES_PATH

    numbers: list = []
    collect_numbers(yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")), numbers)
    text = (DATA_DIR / "booking_policies.md").read_text(encoding="utf-8")
    missing = [n for n in numbers if not re.search(rf"(?<![\d.]){re.escape(str(n))}(?![\d])", text)]
    assert missing == []


def test_policy_file_has_enough_numbered_rules() -> None:
    text = (DATA_DIR / "booking_policies.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^BP-\d+\.\d+ ", text, flags=re.M)) >= 35


def test_search_ranks_released_rooms_and_explains_rejections(index) -> None:
    window = (at("2026-11-18", "11:00"), at("2026-11-18", "12:00"))
    outcome = search_free_rooms(index, SearchRequest(windows=[window], attendees=50, types=["classroom"]), RULES)
    assert outcome.hits and outcome.rejected
    assert all("busy" in r.reason or "seats" in r.reason or "lacks" in r.reason for r in outcome.rejected)
    scores = [h.score for h in outcome.hits]
    assert scores == sorted(scores, reverse=True)


def test_cancelled_class_frees_room_as_released(index) -> None:
    snapshot = index.snapshot
    exception = next(e for e in snapshot.exceptions if e.type == "cancelled" and e.status == "APPROVED")
    entry = snapshot.entry(exception.entry_id)
    start = datetime(exception.date.year, exception.date.month, exception.date.day) + timedelta(minutes=entry.start_min)
    end = datetime(exception.date.year, exception.date.month, exception.date.day) + timedelta(minutes=entry.end_min)
    assert index.check(entry.venue_id, start, end).state == "FREE_RELEASED"


def test_ghost_classes_are_planted_and_busy_until_released(index, readonly_session) -> None:
    snapshot = index.snapshot
    samples = {(s.venue_id, s.ts_hour): s.headcount for s in readonly_session.exec(select(t.OccupancySample))}
    ghosts = detect_ghosts(snapshot, samples, RULES, snapshot.now.date())
    assert len(ghosts) == 6
    entry = ghosts[0].entry
    day = snapshot.now.date() + timedelta(days=(entry.weekday - snapshot.now.weekday()) % 7 + 7)
    start = datetime(day.year, day.month, day.day) + timedelta(minutes=entry.start_min)
    availability = index.check(entry.venue_id, start, start + timedelta(minutes=entry.end_min - entry.start_min))
    assert not availability.free
    assert any(b.ghost for b in availability.blockers)


def test_policy_flags_lead_time_eligibility_and_sponsor(index) -> None:
    snapshot = index.snapshot
    lab = next(v for v in snapshot.venues if v.type == "lab" and v.lab_type == "chem")
    request = BookingRequest("venue", lab.id, snapshot.now + timedelta(hours=2), snapshot.now + timedelta(hours=4), attendees=20, requester_role="student", requester_dept="CSE")
    codes = {v.code for v in policy.check(request, snapshot, RULES, snapshot.now)}
    assert {"P-LEAD", "P-SPONSOR", "P-ELIGIBILITY"} <= codes


def test_policy_capacity_and_duration(index) -> None:
    snapshot = index.snapshot
    classroom = next(v for v in snapshot.venues if v.type == "classroom")
    request = BookingRequest("venue", classroom.id, at("2026-12-01", "10:00"), at("2026-12-01", "15:00"), attendees=classroom.capacity + 5)
    codes = {v.code for v in policy.check(request, snapshot, RULES, snapshot.now)}
    assert {"P-CAPACITY", "P-DURATION"} <= codes


def test_guest_nights_need_a_host(index) -> None:
    snapshot = index.snapshot
    request = BookingRequest("guest_room", 1, at("2026-12-10", "14:00"), at("2026-12-18", "11:00"), attendees=1)
    codes = {v.code for v in policy.check(request, snapshot, RULES, snapshot.now)}
    assert {"P-GUEST-LINK", "P-GUEST-STAY"} <= codes


def test_alternatives_are_ranked_cited_and_valid(index) -> None:
    snapshot = index.snapshot
    amphitheatre = next(v for v in snapshot.venues if v.code == "AMP-1")
    request = BookingRequest("venue", amphitheatre.id, at("2026-11-18", "10:00"), at("2026-11-18", "12:00"), attendees=150, requester_role="faculty")
    assert not check_request(index, RULES, request).ok
    options = recommend_alternatives(index, RULES, request)
    assert len(options) >= 2
    assert [o.cost for o in options] == sorted(o.cost for o in options)
    assert all(o.citations and o.summary() != "same as requested" for o in options)
    for option in options:
        for part in option.requests:
            assert check_request(index, RULES, part).ok


def test_cohort_slots_are_common_free_and_have_rooms(index) -> None:
    snapshot = index.snapshot
    sections = [s.id for s in snapshot.sections.values() if s.dept == "CSE" and s.semester == 5]
    result = find_common_slots(index, RULES, CohortRequest(sections, date(2026, 11, 17), date(2026, 11, 27), 60))
    assert result["slots"]
    by_section = {sid: [e for e in snapshot.entries if e.section_id == sid] for sid in sections}
    for slot in result["slots"]:
        day = date.fromisoformat(slot["date"])
        start = datetime.fromisoformat(slot["start"])
        minutes = start.hour * 60 + start.minute
        for entries in by_section.values():
            for entry in entries:
                if entry.weekday == day.weekday():
                    assert entry.end_min <= minutes or entry.start_min >= minutes + 60
        assert slot["rooms"]


def test_group_allocation_beats_or_matches_greedy(index) -> None:
    snapshot = index.snapshot
    start, end = at("2026-12-10", "14:00"), at("2026-12-12", "11:00")
    rooms = guesthouse.available_rooms(snapshot, RULES, start, end)
    guests = [guesthouse.GuestSpec(f"G{n}", "vip" if n < 2 else "other") for n in range(6)] + [guesthouse.GuestSpec("Access", "other", True)]
    smart = guesthouse.group_allocate(rooms, guests, [(2, 3)], [(4, 5)])
    naive = guesthouse.greedy_allocate(rooms, guests, [(4, 5)])
    assert smart.status in ("OPTIMAL", "FEASIBLE")
    assert smart.assignments[2] == smart.assignments[3]
    assert smart.assignments[4] != smart.assignments[5]
    assert smart.rooms_used <= naive.rooms_used
    assert smart.suite_misuse <= naive.suite_misuse


def test_overlapping_guest_nights_are_rejected(index) -> None:
    snapshot = index.snapshot
    existing = next(b for b in snapshot.bookings if b.resource_type == "guest_room" and b.status == "CONFIRMED")
    assert not guesthouse.room_available(snapshot, RULES, existing.resource_id, existing.start_dt, existing.end_dt)
    assert guesthouse.room_available(snapshot, RULES, existing.resource_id, existing.end_dt + timedelta(hours=3), existing.end_dt + timedelta(days=1))


def test_waitlist_promotes_when_room_frees(index) -> None:
    snapshot = index.snapshot
    blocking = next(b for b in snapshot.bookings if b.resource_type == "guest_room" and b.resource_id == 16 and b.status == "CONFIRMED")
    import dataclasses

    released = dataclasses.replace(snapshot, bookings=[dataclasses.replace(b, status="CANCELLED") if b.id == blocking.id else b for b in snapshot.bookings])
    proposals = guesthouse.promotion_candidates(released, RULES)
    assert proposals and proposals[0]["room_code"]


def test_parking_respects_walkin_reserve_and_splits(index) -> None:
    snapshot = index.snapshot
    start, end = at("2026-12-08", "09:00"), at("2026-12-08", "13:00")
    plan = parking.check_parking(snapshot, RULES, start, end, {"car": 70}, near_venue_id=next(v.id for v in snapshot.venues if v.code == "AMP-1"))
    assert plan.ok and len(plan.allocations) >= 1
    lots = {l.id: l for l in snapshot.lots}
    for allocation in plan.allocations:
        assert allocation.vehicles["car"] <= parking.reservable_capacity(lots[allocation.lot_id], "car", RULES)
    over = parking.check_parking(snapshot, RULES, start, end, {"car": 500})
    assert over.unmet["car"] > 0
    buses = parking.check_parking(snapshot, RULES, start, end, {"bus": 2})
    assert buses.ok and all(lots[a.lot_id].cap_bus > 0 for a in buses.allocations)


def test_bundle_plan_covers_event_and_suggests_related(index) -> None:
    snapshot = index.snapshot
    hall = next(v for v in snapshot.venues if v.code == "AMP-1")
    event = BookingRequest("venue", hall.id, at("2026-12-03", "10:00"), at("2026-12-03", "17:00"), attendees=80, requester_role="faculty", requester_dept="CSE")
    nights = BookingRequest("guest_room", 4, at("2026-12-02", "14:00"), at("2026-12-04", "11:00"), attendees=2, meta={"guests": 2})
    cars = BookingRequest("parking", 1, at("2026-12-03", "09:00"), at("2026-12-03", "18:00"), attendees=80, qty=12, meta={"vehicles": {"car": 12}})
    proposal = plan_bundle(index, RULES, "AI Workshop", [event, nights, cars], external_speakers=2)
    assert proposal.ok, proposal.as_dict(index)
    short_nights = BookingRequest("guest_room", 4, at("2026-12-03", "14:00"), at("2026-12-04", "11:00"), attendees=2, meta={"guests": 2})
    broken = plan_bundle(index, RULES, "AI Workshop", [event, short_nights, cars])
    assert any(v.code == "P-BUNDLE-WINDOW" for v in broken.bundle_violations)


def test_batch_optimiser_is_at_least_as_good_as_greedy(index) -> None:
    events = batch.build_events(index, RULES, 25, seed=11, first_day=date(2026, 12, 1))
    outcome = batch.compare(index, RULES, events, time_limit=5, workers=4)
    assert outcome["cp_sat"]["accepted"] >= outcome["greedy"]["accepted"]
    chosen = {a["event_id"]: a for a in outcome["cp_sat"]["assignments"]}
    spans = sorted((a["venue_id"], a["start"], a["end"]) for a in chosen.values())
    for first, second in zip(spans, spans[1:]):
        if first[0] == second[0]:
            assert first[2] <= second[1]


def test_building_closure_proposes_conflict_free_rehoming(index) -> None:
    snapshot = index.snapshot
    labs = [v.id for v in snapshot.venues if v.building_id == 6]
    closure = impact.Closure("venue", at("2026-11-18", "00:00"), at("2026-11-20", "00:00"), venue_ids=labs, description="Lab Complex 1 closed")
    report = impact.assess(index, RULES, closure, time_limit=5, workers=4)
    assert report["affected"] > 0 and report["resolved"] > 0
    taken = set()
    for item in report["items"]:
        if item["proposal"]:
            key = (item["proposal"]["venue_id"], item["proposal"]["start"])
            assert key not in taken
            taken.add(key)


def test_heatmap_counts_free_classrooms(index) -> None:
    heat = free_room_heatmap(index, RULES, date(2026, 11, 16), date(2026, 11, 28))
    assert heat["total_rooms"] > 30
    assert all(0 <= cell["free_rooms"] <= heat["total_rooms"] for cell in heat["cells"])


def test_validator_green_on_seed(index) -> None:
    assert validator.validate(index.snapshot, RULES) == []
