from datetime import datetime

from app.engine.availability import AvailabilityIndex
from app.engine.search import SearchOutcome
from app.engine.types import Segment


def explain_busy(venue_code: str, blockers: list[Segment], redact: bool = False) -> str:
    if not blockers:
        return f"{venue_code} is free"
    if redact:
        return f"{venue_code} is busy"
    return "; ".join(f"{venue_code} busy {b.time_text()}: {b.label} ({b.layer})" for b in blockers)


def explain_window(index: AvailabilityIndex, venue_id: int, start: datetime, end: datetime, redact: bool = False) -> dict:
    venue = index.snapshot.venue(venue_id)
    availability = index.check(venue_id, start, end)
    return {
        "venue": venue.code, "state": availability.state, "free": availability.free,
        "explanation": explain_busy(venue.code, availability.blockers, redact),
        "blockers": [] if redact else [b.as_dict() for b in availability.blockers],
    }


def why_not(outcome: SearchOutcome, redact: bool = False) -> list[dict]:
    return [
        {"venue": r.venue.code, "reason": f"{r.venue.code} busy {r.time} ({r.layer})" if redact and r.layer else r.reason, "layer": r.layer, "ghost": r.ghost}
        for r in outcome.rejected
    ]


def hit_card(hit) -> dict:
    return {
        "venue_id": hit.venue.id, "code": hit.venue.code, "name": hit.venue.name, "type": hit.venue.type, "building_id": hit.venue.building_id,
        "capacity": hit.venue.capacity, "features": list(hit.venue.features), "state": hit.state, "score": hit.score, "reasons": hit.reasons,
        "walking_min": hit.walking_min, "warnings": [w.as_dict() for w in hit.warnings],
    }
