from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

RULES_PATH = Path(__file__).resolve().parent / "config" / "rules.yaml"


class HoursRule(BaseModel):
    start: str
    end: str


class ResourceRule(BaseModel):
    lead_time_hours: int
    max_advance_days: int
    max_duration_min: int = 0
    setup_buffer_min: int = 0
    teardown_buffer_min: int = 0
    min_fill_ratio: float = 0.0
    dean_approval_above_attendees: int = 0
    max_stay_nights: int = 0
    turnover_buffer_min: int = 0
    checkin_time: str = "14:00"
    checkout_time: str = "11:00"
    approval_chain: list[str]


class GhostRule(BaseModel):
    threshold: float
    min_low_occurrences: int
    window_occurrences: int


class BundleRule(BaseModel):
    parking_suggest_attendees: int
    evening_after: str


class AlternativeWeights(BaseModel):
    max_time_shift_min: int
    max_day_shift: int
    shift_time_per_15min: int
    shift_day_per_day: int
    other_venue: int
    other_building: int
    substitute_type: int
    drop_feature: int
    shorten_per_15min: int
    split_venues: int


class SearchWeights(BaseModel):
    capacity_fit: int
    features: int
    distance: int
    warnings: int
    released_penalty: int
    ideal_fill_low: float
    ideal_fill_high: float


class CohortWeights(BaseModel):
    lunch_penalty: int
    late_penalty: int
    gap_penalty_per_hour: int
    distance_per_min: int
    late_after: str


class Rules(BaseModel):
    timezone: str
    slot_minutes: int
    bookable_hours: HoursRule
    lunch: HoursRule
    periods: list[list[str]]
    fire_safety_cap_pct: int
    hold_ttl_hours: int
    escalation_after_hours: int
    no_show_grace_min: int
    walkin_reserve_pct: int
    ghost: GhostRule
    resources: dict[str, ResourceRule]
    priority_classes: dict[str, int]
    bundles: BundleRule
    alternatives: AlternativeWeights
    search_weights: SearchWeights
    cohort_weights: CohortWeights

    def for_venue_type(self, venue_type: str) -> ResourceRule:
        return self.resources[venue_type]


@lru_cache
def load_rules() -> Rules:
    return Rules.model_validate(yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")))
