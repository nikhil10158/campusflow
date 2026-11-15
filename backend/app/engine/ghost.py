from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.engine.types import EntryInfo, Snapshot
from app.rules import Rules

Samples = dict[tuple[int, datetime], int]


@dataclass
class GhostFinding:
    entry: EntryInfo
    section_size: int
    occurrences: list[dict] = field(default_factory=list)
    mean_ratio: float = 0.0
    low_count: int = 0
    weekly_hours: float = 0.0


def hours_covered(entry: EntryInfo) -> range:
    return range(entry.start_min // 60, (entry.end_min - 1) // 60 + 1)


def past_occurrences(snapshot: Snapshot, entry: EntryInfo, as_of: date, wanted: int) -> list[date]:
    cancelled = {e.date for e in snapshot.exceptions if e.entry_id == entry.id and e.status == "APPROVED" and e.type in ("cancelled", "released", "moved")}
    found: list[date] = []
    day = as_of - timedelta(days=1)
    while len(found) < wanted and day >= entry.effective_from:
        if day.weekday() == entry.weekday and day <= entry.effective_to and day not in snapshot.holidays and day not in cancelled:
            found.append(day)
        day -= timedelta(days=1)
    return found


def occurrence_ratio(entry: EntryInfo, size: int, day: date, samples: Samples) -> float | None:
    counts = [samples[(entry.venue_id, datetime(day.year, day.month, day.day, hour))] for hour in hours_covered(entry) if (entry.venue_id, datetime(day.year, day.month, day.day, hour)) in samples]
    if not counts or size <= 0:
        return None
    return sum(counts) / len(counts) / size


def detect_ghosts(snapshot: Snapshot, samples: Samples, rules: Rules, as_of: date) -> list[GhostFinding]:
    findings: list[GhostFinding] = []
    for entry in snapshot.entries:
        section = snapshot.sections.get(entry.section_id)
        if section is None:
            continue
        measured: list[dict] = []
        for day in past_occurrences(snapshot, entry, as_of, rules.ghost.window_occurrences):
            ratio = occurrence_ratio(entry, section.size, day, samples)
            if ratio is not None:
                measured.append({"date": day.isoformat(), "ratio": round(ratio, 3)})
        lows = [m for m in measured if m["ratio"] < rules.ghost.threshold]
        if len(lows) >= rules.ghost.min_low_occurrences:
            mean = sum(m["ratio"] for m in measured) / len(measured)
            findings.append(GhostFinding(entry, section.size, measured, round(mean, 3), len(lows), (entry.end_min - entry.start_min) / 60))
    findings.sort(key=lambda f: f.mean_ratio)
    return findings


def projected_uplift_hours(findings: list[GhostFinding]) -> float:
    return round(sum(f.weekly_hours for f in findings), 2)
