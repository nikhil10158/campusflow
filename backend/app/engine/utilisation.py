from collections import defaultdict
from datetime import date, datetime

import numpy as np

from app.engine.availability import TEACHING_MASKS, AvailabilityIndex
from app.engine.timeutil import ceil_slot, date_range, floor_slot, parse_hhmm
from app.engine.types import Snapshot
from app.rules import Rules

ROOM_TYPES = ("classroom", "seminar_hall")
UNUSABLE_GAP_SLOTS = 4


def teaching_days(index: AvailabilityIndex, start: date, end: date) -> list[date]:
    snapshot = index.snapshot
    return [d for d in date_range(max(start, index.start), min(end, index.end)) if d.weekday() != 6 and d not in snapshot.holidays]


def venue_utilisation(index: AvailabilityIndex, start: date, end: date, types: tuple[str, ...] = ROOM_TYPES) -> list[dict]:
    snapshot = index.snapshot
    rows = []
    for venue in snapshot.venues:
        if venue.type in types:
            rows.append({
                "venue_id": venue.id, "code": venue.code, "type": venue.type, "building_id": venue.building_id,
                "timetable": round(index.utilisation(venue.id, start, end, timetable_only=True), 3),
                "total": round(index.utilisation(venue.id, start, end), 3),
            })
    return rows


def group_mean(rows: list[dict], key: str, value: str = "total") -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row[value])
    return {name: round(sum(values) / len(values), 3) for name, values in grouped.items()}


def period_windows(rules: Rules) -> list[tuple[int, int]]:
    return [(floor_slot(parse_hhmm(a)), ceil_slot(parse_hhmm(b))) for a, b in rules.periods]


def free_room_heatmap(index: AvailabilityIndex, rules: Rules, start: date, end: date, types: tuple[str, ...] = ROOM_TYPES) -> dict:
    snapshot = index.snapshot
    venues = [index.venue_pos[v.id] for v in snapshot.venues if v.type in types and v.bookable]
    periods = period_windows(rules)
    sums = np.zeros((6, len(periods)))
    counts = np.zeros(6)
    for day in teaching_days(index, start, end):
        weekday = day.weekday()
        offset = index.offset(day)
        busy = index.busy[venues, offset]
        for number, (low, high) in enumerate(periods):
            if weekday == 5 and number >= 4:
                continue
            sums[weekday, number] += int((~busy[:, low:high].any(axis=1)).sum())
        counts[weekday] += 1
    cells = []
    for weekday in range(6):
        for number in range(len(periods)):
            if weekday == 5 and number >= 4:
                continue
            average = sums[weekday, number] / counts[weekday] if counts[weekday] else 0
            cells.append({"weekday": weekday, "period": number, "start": rules.periods[number][0], "end": rules.periods[number][1], "free_rooms": round(float(average), 1)})
    return {"total_rooms": len(venues), "periods": rules.periods, "cells": cells}


def fragmentation(index: AvailabilityIndex, start: date, end: date, types: tuple[str, ...] = ROOM_TYPES) -> dict:
    snapshot = index.snapshot
    gap_slots = 0
    free_slots = 0
    for venue in snapshot.venues:
        if venue.type not in types:
            continue
        position = index.venue_pos[venue.id]
        for day in teaching_days(index, start, end):
            row = index.busy[position, index.offset(day)]
            mask = TEACHING_MASKS[day.weekday() == 5]
            free = (~row) & mask
            free_slots += int(free.sum())
            run = 0
            for slot in range(len(row)):
                if free[slot]:
                    run += 1
                    continue
                if 0 < run < UNUSABLE_GAP_SLOTS:
                    gap_slots += run
                run = 0
            if 0 < run < UNUSABLE_GAP_SLOTS:
                gap_slots += run
    return {"unusable_gap_hours": round(gap_slots / 4, 1), "free_hours": round(free_slots / 4, 1), "fragmentation_ratio": round(gap_slots / free_slots, 3) if free_slots else 0.0}


def seat_utilisation(snapshot: Snapshot, samples: dict[tuple[int, datetime], int], start: date, end: date) -> float:
    capacities = {v.id: v.capacity for v in snapshot.venues}
    ratios = [count / capacities[venue_id] for (venue_id, stamp), count in samples.items() if start <= stamp.date() <= end and capacities.get(venue_id)]
    return round(sum(ratios) / len(ratios), 3) if ratios else 0.0


def hourly_profile(index: AvailabilityIndex, start: date, end: date, types: tuple[str, ...] = ROOM_TYPES) -> list[dict]:
    snapshot = index.snapshot
    positions = [index.venue_pos[v.id] for v in snapshot.venues if v.type in types]
    days = teaching_days(index, start, end)
    profile = []
    for hour in range(7, 22):
        used = 0
        total = 0
        for day in days:
            block = index.busy[positions, index.offset(day), hour * 4:(hour + 1) * 4]
            used += int(block.any(axis=1).sum())
            total += len(positions)
        profile.append({"hour": hour, "utilisation": round(used / total, 3) if total else 0.0})
    return profile
