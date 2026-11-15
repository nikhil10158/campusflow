from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from app.engine.availability import AvailabilityIndex
from app.engine.search import SearchRequest, search_free_rooms, walking_minutes
from app.engine.timeutil import SLOTS_PER_DAY, at_minute, ceil_slot, date_range, floor_slot, parse_hhmm
from app.engine.types import Snapshot
from app.rules import Rules

NO_CLASS_DAY_GAP_MIN = 180
PERIOD_BREAK_MIN = 5
MAX_ROOM_SEARCHES = 40
ROOMS_PER_SLOT = 3


@dataclass
class CohortRequest:
    section_ids: list[int]
    start_date: date
    end_date: date
    duration_min: int
    faculty_ids: list[int] = field(default_factory=list)
    earliest: str = "09:00"
    latest: str = "18:00"
    attendees: int | None = None


@dataclass
class SlotOption:
    day: date
    start_min: int
    end_min: int
    score: float
    rooms: list[dict]
    reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "date": self.day.isoformat(),
            "start": at_minute(self.day, self.start_min).isoformat(),
            "end": at_minute(self.day, self.end_min).isoformat(),
            "score": round(self.score, 1),
            "rooms": self.rooms,
            "reasons": self.reasons,
        }


def class_mask(snapshot: Snapshot, entries: list, day: date, cleared: set[tuple[int, date]]) -> np.ndarray:
    mask = np.zeros(SLOTS_PER_DAY, dtype=bool)
    for entry in entries:
        if entry.weekday == day.weekday() and entry.effective_from <= day <= entry.effective_to and (entry.id, day) not in cleared:
            mask[floor_slot(entry.start_min):ceil_slot(entry.end_min)] = True
    return mask


def cleared_pairs(snapshot: Snapshot) -> set[tuple[int, date]]:
    return {(e.entry_id, e.date) for e in snapshot.exceptions if e.status == "APPROVED" and e.type in ("cancelled", "released", "moved")}


def heat_strip(free_counts: np.ndarray) -> list[int]:
    return [int(value) for value in free_counts]


def gap_minutes(entries: list, day: date, start_min: int, end_min: int, cleared: set[tuple[int, date]]) -> int:
    today = [e for e in entries if e.weekday == day.weekday() and e.effective_from <= day <= e.effective_to and (e.id, day) not in cleared]
    if not today:
        return NO_CLASS_DAY_GAP_MIN
    distances: list[int] = []
    for entry in today:
        if entry.end_min <= start_min:
            distances.append(start_min - entry.end_min)
        elif entry.start_min >= end_min:
            distances.append(entry.start_min - end_min)
        else:
            distances.append(0)
    return max(0, min(distances) - PERIOD_BREAK_MIN)


def find_common_slots(index: AvailabilityIndex, rules: Rules, request: CohortRequest, limit: int = 8) -> dict:
    snapshot = index.snapshot
    weights = rules.cohort_weights
    cleared = cleared_pairs(snapshot)
    by_section = {sid: [e for e in snapshot.entries if e.section_id == sid] for sid in request.section_ids}
    by_faculty = {fid: [e for e in snapshot.entries if e.faculty_id == fid] for fid in request.faculty_ids}
    attendees = request.attendees or sum(snapshot.sections[sid].size for sid in request.section_ids)
    need_slots = ceil_slot(request.duration_min)
    first_slot = ceil_slot(parse_hhmm(request.earliest))
    last_slot = floor_slot(parse_hhmm(request.latest))
    lunch_low = floor_slot(parse_hhmm(rules.lunch.start))
    lunch_high = ceil_slot(parse_hhmm(rules.lunch.end))
    late_after = ceil_slot(parse_hhmm(weights.late_after))
    candidates: list[tuple[float, date, int, int, list[str]]] = []
    strips: dict[str, list[int]] = {}
    for day in date_range(request.start_date, request.end_date):
        if day.weekday() == 6 or day in snapshot.holidays:
            continue
        masks = [class_mask(snapshot, by_section[sid], day, cleared) for sid in request.section_ids]
        masks += [class_mask(snapshot, by_faculty[fid], day, cleared) for fid in request.faculty_ids]
        stacked = np.array(masks)
        strips[day.isoformat()] = heat_strip((~stacked[:len(request.section_ids)]).sum(axis=0))
        blocked = stacked.any(axis=0)
        for low in range(first_slot, last_slot - need_slots + 1):
            high = low + need_slots
            if blocked[low:high].any():
                continue
            score = 100.0
            reasons = ["every section and teacher is free"]
            if low < lunch_high and high > lunch_low:
                score -= weights.lunch_penalty
                reasons.append("overlaps lunch")
            if high > late_after:
                score -= weights.late_penalty
                reasons.append("ends late in the day")
            gaps = [gap_minutes(by_section[sid], day, low * 15, high * 15, cleared) for sid in request.section_ids]
            average_gap = sum(gaps) / len(gaps)
            score -= weights.gap_penalty_per_hour * average_gap / 60
            if average_gap == 0:
                reasons.append("sits right next to an existing class")
            candidates.append((score, day, low * 15, high * 15, reasons))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    options: list[SlotOption] = []
    homes = [snapshot.sections[sid].home_venue_id for sid in request.section_ids if snapshot.sections[sid].home_venue_id]
    for score, day, start_min, end_min, reasons in candidates[:MAX_ROOM_SEARCHES]:
        window = (at_minute(day, start_min), at_minute(day, end_min))
        outcome = search_free_rooms(index, SearchRequest(windows=[window], attendees=attendees, types=["classroom", "seminar_hall"]), rules)
        rooms = []
        for hit in outcome.hits:
            walk = [walking_minutes(snapshot, snapshot.venue(h).building_id, hit.venue.building_id) for h in homes]
            average_walk = sum(walk) / len(walk) if walk else 0
            rooms.append((hit.score - weights.distance_per_min * average_walk, hit, average_walk))
        rooms.sort(key=lambda item: -item[0])
        if not rooms:
            continue
        best_walk = rooms[0][2]
        options.append(SlotOption(
            day, start_min, end_min, score - weights.distance_per_min * best_walk,
            [{"venue_id": h.venue.id, "code": h.venue.code, "capacity": h.venue.capacity, "state": h.state, "walk_min": round(w, 1)} for _, h, w in rooms[:ROOMS_PER_SLOT]],
            reasons + [f"{rooms[0][1].venue.code} is free ({best_walk:.0f} min average walk from home rooms)"],
        ))
    options.sort(key=lambda option: (-option.score, option.day, option.start_min))
    return {"attendees": attendees, "slots": [o.as_dict() for o in options[:limit]], "heat_strips": strips, "sections": len(request.section_ids)}
