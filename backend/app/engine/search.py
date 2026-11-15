import math
from dataclasses import dataclass, field
from datetime import datetime

from app.engine.availability import AvailabilityIndex
from app.engine.policy import venue_warnings
from app.engine.types import Snapshot, VenueInfo, Violation
from app.rules import Rules

WALKING_METRES_PER_MIN = 80
DEFAULT_TYPES = ["classroom", "seminar_hall"]


@dataclass
class SearchRequest:
    windows: list[tuple[datetime, datetime]]
    attendees: int = 0
    types: list[str] = field(default_factory=lambda: list(DEFAULT_TYPES))
    required_features: tuple[str, ...] = ()
    optional_features: tuple[str, ...] = ()
    near_venue_id: int | None = None
    building_id: int | None = None
    dept: str | None = None
    accessible: bool = False


@dataclass
class SearchHit:
    venue: VenueInfo
    state: str
    score: float
    reasons: list[str]
    walking_min: int | None
    warnings: list[Violation]


@dataclass
class Rejection:
    venue: VenueInfo
    reason: str
    layer: str | None = None
    ghost: bool = False
    time: str | None = None


@dataclass
class SearchOutcome:
    hits: list[SearchHit]
    rejected: list[Rejection]


def walking_minutes(snapshot: Snapshot, building_a: int, building_b: int) -> int:
    if building_a == building_b:
        return 1
    a = snapshot.buildings[building_a]
    b = snapshot.buildings[building_b]
    return max(1, math.ceil(math.hypot(a.x - b.x, a.y - b.y) / WALKING_METRES_PER_MIN))


def fit_score(attendees: int, capacity: int, rules: Rules) -> float:
    if attendees <= 0 or capacity <= 0:
        return 1.0
    ratio = attendees / capacity
    low = rules.search_weights.ideal_fill_low
    high = rules.search_weights.ideal_fill_high
    if ratio < low:
        return ratio / low
    if ratio <= high:
        return 1.0
    return max(0.0, 1.0 - (ratio - high) / (1.0 - high) * 0.5)


def static_rejection(venue: VenueInfo, request: SearchRequest, rules: Rules) -> str | None:
    if not venue.bookable:
        return f"{venue.code} is not bookable"
    if request.attendees * 100 > venue.capacity * rules.fire_safety_cap_pct:
        return f"{venue.code} seats {venue.capacity}, fewer than the {request.attendees} attendees"
    missing = [f for f in request.required_features if f not in venue.features]
    if missing:
        return f"{venue.code} lacks required features: {', '.join(missing)}"
    if request.accessible and not venue.accessible:
        return f"{venue.code} is not accessible"
    if venue.type == "lab" and request.dept and request.dept not in venue.eligible_depts:
        return f"{venue.code} is not open to the {request.dept} department"
    return None


def search_free_rooms(index: AvailabilityIndex, request: SearchRequest, rules: Rules) -> SearchOutcome:
    snapshot = index.snapshot
    near_building = snapshot.venue(request.near_venue_id).building_id if request.near_venue_id else request.building_id
    hits: list[SearchHit] = []
    rejected: list[Rejection] = []
    for venue in snapshot.venues:
        if venue.type not in request.types:
            continue
        reason = static_rejection(venue, request, rules)
        if reason:
            rejected.append(Rejection(venue, reason))
            continue
        states: list[str] = []
        blocked: Rejection | None = None
        for start, end in request.windows:
            availability = index.check(venue.id, start, end)
            if not availability.free:
                blocker = availability.blockers[0]
                text = f"{venue.code} busy {blocker.time_text()} on {start:%d %b}: {blocker.label} ({blocker.layer})"
                if blocker.ghost:
                    text += " - ghost class candidate, release needs approval"
                blocked = Rejection(venue, text, blocker.layer, blocker.ghost, blocker.time_text())
                break
            states.append(availability.state)
        if blocked:
            rejected.append(blocked)
            continue
        state = "FREE_RELEASED" if "FREE_RELEASED" in states else "FREE"
        hits.append(score_hit(snapshot, venue, state, request, near_building, rules))
    hits.sort(key=lambda hit: (-hit.score, hit.venue.code))
    return SearchOutcome(hits, rejected)


def score_hit(snapshot: Snapshot, venue: VenueInfo, state: str, request: SearchRequest, near_building: int | None, rules: Rules) -> SearchHit:
    weights = rules.search_weights
    fit = fit_score(request.attendees, venue.capacity, rules)
    wanted = request.optional_features
    matched = [f for f in wanted if f in venue.features]
    features = len(matched) / len(wanted) if wanted else 1.0
    walking = walking_minutes(snapshot, near_building, venue.building_id) if near_building else None
    distance = max(0.0, 1.0 - walking / 15) if walking is not None else 1.0
    warnings = venue_warnings(venue, request.attendees, rules)
    score = fit * weights.capacity_fit + features * weights.features + distance * weights.distance
    score += (0.0 if warnings else 1.0) * weights.warnings
    if state == "FREE_RELEASED":
        score -= weights.released_penalty
    reasons: list[str] = []
    if request.attendees:
        reasons.append(f"Seats {venue.capacity} for {request.attendees} attendees ({request.attendees * 100 // venue.capacity}% full)")
    if matched:
        reasons.append(f"Has {', '.join(matched)}")
    if walking is not None:
        reasons.append(f"{walking} min walk from the reference building")
    if state == "FREE_RELEASED":
        reasons.append("Pre-slotted class was cancelled or released, so the room is bookable")
    reasons.extend(w.message for w in warnings)
    return SearchHit(venue, state, round(score, 2), reasons, walking, warnings)
