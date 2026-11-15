import json
import math
import re

from app.agent.llm import LLMUnavailable, get_llm

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
NARRATIVE_PROMPT = (
    "Write a short utilisation report narrative (4 to 6 sentences) for campus administrators. Use ONLY the numbers in the JSON below, copied exactly. "
    "Do not compute new numbers, do not add dates, and do not invent causes. Mention utilisation, ghost classes, the guest house and parking.\n\nKPI JSON:\n"
)


def number_tokens(text: str) -> set[float]:
    values: set[float] = set()
    for token in NUMBER.findall(text):
        try:
            values.add(float(token.replace(",", "")))
        except ValueError:
            continue
    return values


def allowed_numbers(payload: object, extra: str = "") -> set[float]:
    base = number_tokens(json.dumps(payload, default=str)) | number_tokens(extra)
    allowed = set(base)
    for value in base:
        allowed.add(math.floor(value + 0.5))
        allowed.add(math.floor(value * 10 + 0.5) / 10)
    return allowed


def numbers_verified(text: str, payload: object, extra: str = "") -> bool:
    allowed = allowed_numbers(payload, extra)
    for value in number_tokens(text):
        if not any(abs(value - known) <= 0.051 for known in allowed):
            return False
    return True


def template_narrative(kpis: dict) -> str:
    guest = kpis["guest_house"]
    parking = kpis["parking"]
    return (
        f"Between {kpis['period']['start']} and {kpis['period']['end']}, classroom time utilisation was {kpis['classroom_time_utilisation_pct']}% and seat utilisation was {kpis['seat_utilisation_pct']}%. "
        f"Peak hours ran at {kpis['peak_utilisation_pct']}% against {kpis['off_peak_utilisation_pct']}% off-peak. "
        f"{kpis['ghost_classes']} ghost classes were flagged, and releasing them would free {kpis['ghost_bookable_hours_per_week']} bookable hours per week. "
        f"The guest house was {guest['occupancy_pct']}% occupied with {guest['waitlisted']} request(s) waitlisted. "
        f"Peak car parking use reached {parking['peak_car_utilisation_pct']}% and the no-show rate was {parking['no_show_rate_pct']}%."
    )


def generate_narrative(kpis: dict) -> dict:
    fallback = {"text": template_narrative(kpis), "verified": True, "mode": "template", "attempts": 0}
    llm = get_llm()
    if not llm.usable():
        return fallback
    compact = {k: kpis[k] for k in ("period", "classroom_time_utilisation_pct", "seat_utilisation_pct", "peak_utilisation_pct", "off_peak_utilisation_pct", "ghost_classes", "ghost_bookable_hours_per_week", "guest_house", "parking")}
    for attempt in (1, 2):
        try:
            text = llm.generate(NARRATIVE_PROMPT + json.dumps(compact), cache=attempt == 1).text.strip()
        except LLMUnavailable:
            return fallback
        if text and numbers_verified(text, compact):
            return {"text": text, "verified": True, "mode": "llm", "attempts": attempt}
    return fallback
