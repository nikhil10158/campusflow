import dataclasses
from dataclasses import dataclass, field
from datetime import datetime

from app.engine import policy
from app.engine.alternatives import Alternative, recommend_alternatives, with_window
from app.engine.availability import AvailabilityIndex
from app.engine.proposal import CheckResult, check_request
from app.engine.timeutil import parse_hhmm
from app.engine.types import BookingRequest, Violation
from app.rules import Rules


@dataclass
class BundleProposal:
    title: str
    components: list[CheckResult] = field(default_factory=list)
    bundle_violations: list[Violation] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.components) and not policy.hard_only(self.bundle_violations)

    def as_dict(self, index: AvailabilityIndex) -> dict:
        snapshot = index.snapshot
        parts = []
        for result in self.components:
            request = result.request
            label = snapshot.venue(request.resource_id).code if request.resource_type == "venue" else (
                next((r.code for r in snapshot.guest_rooms if r.id == request.resource_id), "") if request.resource_type == "guest_room"
                else next((l.name for l in snapshot.lots if l.id == request.resource_id), ""))
            parts.append({
                "resource_type": request.resource_type, "resource_id": request.resource_id, "label": label, "title": request.title,
                "start": request.start.isoformat(), "end": request.end.isoformat(), "attendees": request.attendees, "qty": request.qty,
                "meta": request.meta, **result.as_dict(),
            })
        return {
            "title": self.title, "ok": self.ok, "components": parts,
            "bundle_violations": [v.as_dict() for v in self.bundle_violations],
            "suggestions": self.suggestions, "alternatives": self.alternatives,
        }


def event_window(requests: list[BookingRequest]) -> tuple[datetime, datetime] | None:
    venues = [r for r in requests if r.resource_type == "venue"]
    if not venues:
        return None
    return min(r.start for r in venues), max(r.end for r in venues)


def bundle_violations(requests: list[BookingRequest]) -> list[Violation]:
    window = event_window(requests)
    if window is None:
        return []
    start, end = window
    found: list[Violation] = []
    for request in requests:
        if request.resource_type == "guest_room" and not (request.start.date() <= start.date() and request.end.date() >= end.date()):
            found.append(policy.hard("P-BUNDLE-WINDOW", "BP-7.2", "Guest nights must cover the whole event"))
        if request.resource_type == "parking" and not (request.start <= start and request.end >= end):
            found.append(policy.hard("P-BUNDLE-WINDOW", "BP-7.2", "Parking must cover arrival before and departure after the event"))
    return found


def suggest_related(requests: list[BookingRequest], rules: Rules, external_speakers: int = 0, recording: bool = False) -> list[dict]:
    window = event_window(requests)
    if window is None:
        return []
    kinds = {r.resource_type for r in requests}
    attendees = max((r.attendees for r in requests if r.resource_type == "venue"), default=0)
    found: list[dict] = []
    if external_speakers and "guest_room" not in kinds:
        found.append({"resource": "guest_room", "reason": f"{external_speakers} external speaker(s) usually need guest house rooms", "rule_id": "BP-7.6"})
    if attendees > rules.bundles.parking_suggest_attendees and "parking" not in kinds:
        found.append({"resource": "parking", "reason": f"more than {rules.bundles.parking_suggest_attendees} attendees usually need visitor parking", "rule_id": "BP-7.6"})
    evening = parse_hhmm(rules.bundles.evening_after)
    if window[1].hour * 60 + window[1].minute > evening:
        found.append({"resource": "security_notice", "reason": f"the event ends after {rules.bundles.evening_after}, so security should be told", "rule_id": "BP-7.6"})
    if recording:
        found.append({"resource": "av_buffer", "reason": "recording needs audio-visual setup time, already included in the venue buffers", "rule_id": "BP-4.6"})
    return found


def link_components(requests: list[BookingRequest], title: str) -> list[BookingRequest]:
    linked = []
    for request in requests:
        meta = {**request.meta, "bundle_event": title}
        linked.append(dataclasses.replace(request, meta=meta, host_ref=request.host_ref or title))
    return linked


def plan_bundle(index: AvailabilityIndex, rules: Rules, title: str, requests: list[BookingRequest], external_speakers: int = 0, recording: bool = False) -> BundleProposal:
    linked = link_components(requests, title)
    proposal = BundleProposal(title)
    proposal.components = [check_request(index, rules, request) for request in linked]
    proposal.bundle_violations = bundle_violations(linked)
    proposal.suggestions = suggest_related(linked, rules, external_speakers, recording)
    if not proposal.ok:
        proposal.alternatives = bundle_alternatives(index, rules, linked)
    return proposal


def shift_dependents(requests: list[BookingRequest], moved_index: int, new_window: tuple[datetime, datetime]) -> list[BookingRequest]:
    original = requests[moved_index]
    delta_start = new_window[0] - original.start
    delta_end = new_window[1] - original.end
    adjusted = []
    for position, request in enumerate(requests):
        if position == moved_index:
            adjusted.append(with_window(request, start=new_window[0], end=new_window[1]))
        elif request.resource_type in ("guest_room", "parking") and (delta_start or delta_end):
            adjusted.append(with_window(request, start=request.start + delta_start, end=request.end + delta_end))
        else:
            adjusted.append(request)
    return adjusted


def bundle_alternatives(index: AvailabilityIndex, rules: Rules, requests: list[BookingRequest], limit: int = 3) -> list[dict]:
    primary = next((i for i, r in enumerate(requests) if r.resource_type == "venue"), None)
    if primary is None:
        return []
    results: list[dict] = []
    options: list[Alternative] = recommend_alternatives(index, rules, requests[primary], limit=8)
    for option in options:
        if len(option.requests) != 1:
            continue
        candidate = option.requests[0]
        variant = shift_dependents(requests, primary, (candidate.start, candidate.end))
        variant[primary] = with_window(variant[primary], resource_id=candidate.resource_id)
        checks = [check_request(index, rules, r) for r in variant]
        if all(c.ok for c in checks) and not policy.hard_only(bundle_violations(variant)):
            results.append({
                "what_changed": option.summary() + ("; guest nights and parking moved with the event" if variant[primary].start != requests[primary].start else ""),
                "cost": option.cost, "citations": option.citations,
                "components": [{"resource_type": r.resource_type, "resource_id": r.resource_id, "start": r.start.isoformat(), "end": r.end.isoformat(), "qty": r.qty, "attendees": r.attendees, "meta": r.meta} for r in variant],
            })
        if len(results) >= limit:
            break
    return results
