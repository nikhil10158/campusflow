import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from rapidfuzz import fuzz, process
from sqlmodel import Session, select

from app.agent import rag
from app.engine import explain, guesthouse, impact, parking
from app.engine.alternatives import recommend_alternatives
from app.engine.availability import AvailabilityIndex, section_label
from app.engine.bundles import plan_bundle, suggest_related
from app.engine.cohort import CohortRequest, find_common_slots
from app.engine.proposal import check_request
from app.engine.search import SearchRequest, search_free_rooms
from app.engine.types import BookingRequest
from app.models import tables as t
from app.rules import Rules
from app.services import audit, ops, reports
from app.services.bookings import booking_dict, visible_to
from app.services.config import solver_settings

ALL_ROLES = {"admin", "faculty", "approver", "student"}
STAFF = {"admin", "faculty", "approver"}
ADMIN = {"admin"}
ADMIN_APPROVER = {"admin", "approver"}
MAX_HITS = 5
MAX_ITEMS = 12


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    session: Session
    user: t.User
    index: AvailabilityIndex
    rules: Rules
    now: datetime
    proposals: list[dict] = field(default_factory=list)

    @property
    def redact(self) -> bool:
        return self.user.role != "admin"


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    roles: set[str]
    kind: str
    handler: Callable[[ToolContext, dict], dict]


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, parameters: dict, roles: set[str], kind: str = "read") -> Callable:
    def register(handler: Callable[[ToolContext, dict], dict]) -> Callable:
        TOOLS[name] = Tool(name, description, {"type": "object", "properties": parameters, "additionalProperties": False}, roles, kind, handler)
        return handler

    return register


S = {"type": "string"}
N = {"type": "integer"}
ISO = {"type": "string", "description": "ISO 8601 local date-time such as 2026-11-18T14:00:00"}
STRINGS = {"type": "array", "items": {"type": "string"}}
COMPONENT = {
    "type": "object",
    "properties": {
        "resource_type": {"type": "string", "enum": ["venue", "guest_room", "parking"]}, "resource_code": {"type": "string", "description": "Venue code like AMP-1, guest room code like GH-104, or parking lot name"},
        "start": ISO, "end": ISO, "attendees": N, "qty": N, "title": S, "meta": {"type": "object"},
    },
    "required": ["resource_type", "resource_code", "start", "end"],
}


def parse_dt(value: Any, label: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        raise ToolError(f"{label} must be an ISO date-time such as 2026-11-18T14:00:00")


def venue_by_code(ctx: ToolContext, code: Any) -> int:
    key = str(code).strip().upper().replace(" ", "")
    for venue in ctx.index.snapshot.venues:
        if venue.code.replace("-", "") == key.replace("-", "") or str(venue.id) == key:
            return venue.id
    raise ToolError(f"No venue with code {code}")


def resolve_resource(ctx: ToolContext, resource_type: str, code: Any) -> int:
    snapshot = ctx.index.snapshot
    if resource_type == "venue":
        return venue_by_code(ctx, code)
    if resource_type == "guest_room":
        for room in snapshot.guest_rooms:
            if room.code.lower() == str(code).lower() or str(room.id) == str(code):
                return room.id
        raise ToolError(f"No guest room {code}")
    for lot in snapshot.lots:
        if lot.name.lower() == str(code).lower() or str(lot.id) == str(code):
            return lot.id
    match = process.extractOne(str(code), {l.id: l.name for l in snapshot.lots}, scorer=fuzz.WRatio, score_cutoff=70)
    if match:
        return match[2]
    raise ToolError(f"No parking lot {code}")


def request_from_component(ctx: ToolContext, component: dict, sponsor_id: int | None = None) -> BookingRequest:
    resource_type = component.get("resource_type", "venue")
    meta = dict(component.get("meta") or {})
    if resource_type == "parking" and "vehicles" not in meta:
        meta["vehicles"] = {"car": int(component.get("qty", 1))}
    if resource_type == "guest_room":
        meta.setdefault("guests", int(component.get("attendees") or 1))
    return BookingRequest(
        resource_type=resource_type, resource_id=resolve_resource(ctx, resource_type, component.get("resource_code", component.get("resource_id"))),
        start=parse_dt(component.get("start"), "start"), end=parse_dt(component.get("end"), "end"), attendees=int(component.get("attendees") or 0),
        qty=int(component.get("qty") or 1), title=component.get("title", ""), requester_role=ctx.user.role, requester_id=ctx.user.id,
        requester_dept=ctx.user.dept, sponsor_id=component.get("sponsor_id", sponsor_id), host_ref=component.get("host_ref"), meta=meta,
    )


def component_body(request: BookingRequest) -> dict:
    return {
        "resource_type": request.resource_type, "resource_id": request.resource_id, "start": request.start.isoformat(), "end": request.end.isoformat(),
        "event_title": request.title or "Untitled request", "attendees": request.attendees, "qty": request.qty, "sponsor_id": request.sponsor_id,
        "host_ref": request.host_ref, "meta": {k: v for k, v in request.meta.items() if k != "exclude_booking_id"},
    }


def trim_check(result) -> dict:
    return {"ok": result.ok, "state": result.state, "violations": [v.as_dict() for v in result.violations], "conflicts": result.conflicts[:4], "approval_chain": result.approval_chain}


@tool("declare_plan", "Declare the ordered steps you will take before calling other tools.", {"steps": STRINGS, "rationale": S}, ALL_ROLES)
def declare_plan(ctx: ToolContext, args: dict) -> dict:
    return {"plan": list(args.get("steps", [])), "rationale": args.get("rationale", "")}


@tool("resolve_entity", "Fuzzy-match a name to a venue, building, section, faculty member or course. Returns candidates with confidence.", {"kind": {"type": "string", "enum": ["venue", "building", "section", "faculty", "course"]}, "text": S}, ALL_ROLES)
def resolve_entity(ctx: ToolContext, args: dict) -> dict:
    kind, text = args["kind"], str(args["text"])
    snapshot = ctx.index.snapshot
    if kind == "venue":
        pool = {v.id: f"{v.code} {v.name}" for v in snapshot.venues}
    elif kind == "building":
        pool = {b.id: b.name for b in snapshot.buildings.values()}
    elif kind == "section":
        pool = {s.id: section_label(snapshot, s.id) for s in snapshot.sections.values()}
    elif kind == "faculty":
        pool = dict(snapshot.faculty)
    elif kind == "course":
        pool = {c.id: f"{c.code} {c.name}" for c in ctx.session.exec(select(t.Course))}
    else:
        raise ToolError("kind must be venue, building, section, faculty or course")
    matches = process.extract(text, pool, scorer=fuzz.WRatio, limit=3)
    return {"candidates": [{"id": key, "label": label, "confidence": round(score / 100, 2)} for label, score, key in matches]}


@tool("get_timetable", "Weekly timetable of a section or the bookings-free class timetable of a venue.", {"section_id": N, "venue_id": N}, ALL_ROLES)
def get_timetable(ctx: ToolContext, args: dict) -> dict:
    snapshot = ctx.index.snapshot
    if args.get("section_id"):
        entries = [e for e in snapshot.entries if e.section_id == args["section_id"]]
        return {"entries": [{"weekday": e.weekday, "start_min": e.start_min, "end_min": e.end_min, "course": e.course_code, "venue": snapshot.venue(e.venue_id).code} for e in entries][:60]}
    if args.get("venue_id"):
        entries = [e for e in snapshot.entries if e.venue_id == args["venue_id"]]
        return {"entries": [{"weekday": e.weekday, "start_min": e.start_min, "end_min": e.end_min, "label": "Busy" if ctx.redact else e.course_code} for e in entries][:60]}
    raise ToolError("Give a section_id or a venue_id")


@tool("search_free_rooms", "Find genuinely free rooms for a time window, ranked, with reasons and the first blocking reason for rejected rooms.", {
    "start": ISO, "end": ISO, "attendees": N, "types": STRINGS, "required_features": STRINGS, "optional_features": STRINGS, "near_venue_code": S, "building_id": N, "dept": S, "accessible": {"type": "boolean"}, "repeat_weeks": N,
}, ALL_ROLES)
def search_free_rooms_tool(ctx: ToolContext, args: dict) -> dict:
    start, end = parse_dt(args.get("start"), "start"), parse_dt(args.get("end"), "end")
    windows = [(start + timedelta(weeks=n), end + timedelta(weeks=n)) for n in range(max(1, min(int(args.get("repeat_weeks", 1)), 26)))]
    if not all(ctx.index.covers(a, b) for a, b in windows):
        raise ToolError("That date is outside the planning calendar")
    request = SearchRequest(
        windows=windows, attendees=int(args.get("attendees") or 0), types=args.get("types") or ["classroom", "seminar_hall"],
        required_features=tuple(args.get("required_features") or ()), optional_features=tuple(args.get("optional_features") or ()),
        near_venue_id=venue_by_code(ctx, args["near_venue_code"]) if args.get("near_venue_code") else None, building_id=args.get("building_id"), dept=args.get("dept"), accessible=bool(args.get("accessible")),
    )
    outcome = search_free_rooms(ctx.index, request, ctx.rules)
    return {
        "window": [start.isoformat(), end.isoformat()], "free_count": len(outcome.hits), "considered": len(outcome.hits) + len(outcome.rejected),
        "hits": [explain.hit_card(h) | {"venue_code": h.venue.code} for h in outcome.hits[:MAX_HITS]], "why_not": explain.why_not(outcome, ctx.redact)[:6],
    }


@tool("busy_reasons", "Explain why a venue is busy in a window.", {"venue_code": S, "start": ISO, "end": ISO}, ALL_ROLES)
def busy_reasons(ctx: ToolContext, args: dict) -> dict:
    return explain.explain_window(ctx.index, venue_by_code(ctx, args["venue_code"]), parse_dt(args["start"], "start"), parse_dt(args["end"], "end"), redact=ctx.redact)


@tool("find_common_free_slots", "Find common free time for several sections (and optional faculty) and free rooms for it.", {
    "dept": S, "semester": N, "section_names": STRINGS, "faculty_ids": {"type": "array", "items": N}, "start_date": S, "end_date": S, "duration_min": N, "earliest": S, "latest": S,
}, STAFF)
def find_common_free_slots(ctx: ToolContext, args: dict) -> dict:
    sections = [s for s in ctx.index.snapshot.sections.values() if (not args.get("dept") or s.dept == args["dept"]) and (not args.get("semester") or s.semester == int(args["semester"])) and (not args.get("section_names") or s.name in args["section_names"])]
    if not sections:
        raise ToolError("No sections match that description")
    request = CohortRequest([s.id for s in sections], date.fromisoformat(args["start_date"]), date.fromisoformat(args["end_date"]), int(args.get("duration_min", 60)), list(args.get("faculty_ids") or []), args.get("earliest", "09:00"), args.get("latest", "18:00"))
    result = find_common_slots(ctx.index, ctx.rules, request, limit=5)
    result["heat_strips"] = dict(list(result["heat_strips"].items())[:3])
    result["section_labels"] = [section_label(ctx.index.snapshot, s.id) for s in sections]
    return result


@tool("check_policy", "Check one booking request against policy and availability without storing anything.", {"component": COMPONENT}, ALL_ROLES)
def check_policy(ctx: ToolContext, args: dict) -> dict:
    return trim_check(check_request(ctx.index, ctx.rules, request_from_component(ctx, args["component"])))


@tool("check_guesthouse", "List guest house rooms free for the nights, best fit first, with tariff estimate.", {"start": ISO, "end": ISO, "guests": N, "category": S, "accessible": {"type": "boolean"}}, STAFF | {"student"})
def check_guesthouse(ctx: ToolContext, args: dict) -> dict:
    start, end = parse_dt(args["start"], "start"), parse_dt(args["end"], "end")
    rooms = guesthouse.best_fit(ctx.index.snapshot, ctx.rules, start, end, int(args.get("guests", 1)), args.get("category", "other"), bool(args.get("accessible")))
    return {"rooms": [{"code": r.code, "type": r.type, "capacity": r.capacity, "accessible": r.accessible, "estimate": guesthouse.tariff_estimate(r, start, end)} for r in rooms[:MAX_HITS]], "free_count": len(rooms)}


@tool("check_parking", "Plan visitor parking by lot proximity and capacity (walk-in reserve respected).", {"start": ISO, "end": ISO, "vehicles": {"type": "object"}, "near_venue_code": S}, ALL_ROLES)
def check_parking_tool(ctx: ToolContext, args: dict) -> dict:
    near = venue_by_code(ctx, args["near_venue_code"]) if args.get("near_venue_code") else None
    plan = parking.check_parking(ctx.index.snapshot, ctx.rules, parse_dt(args["start"], "start"), parse_dt(args["end"], "end"), {k: int(v) for k, v in dict(args["vehicles"]).items()}, near)
    return {"ok": plan.ok, "unmet": plan.unmet, "allocations": [{"lot_id": a.lot_id, "lot": a.lot_name, "vehicles": a.vehicles, "distance_m": a.distance_m, "shuttle": a.shuttle} for a in plan.allocations]}


@tool("suggest_related", "Suggest related resources (guest house, parking, security notice) for an event.", {"components": {"type": "array", "items": COMPONENT}, "external_speakers": N, "recording": {"type": "boolean"}}, STAFF | {"student"})
def suggest_related_tool(ctx: ToolContext, args: dict) -> dict:
    requests = [request_from_component(ctx, c) for c in args["components"]]
    return {"suggestions": suggest_related(requests, ctx.rules, int(args.get("external_speakers", 0)), bool(args.get("recording")))}


@tool("recommend_alternatives", "Ranked alternatives for a request that cannot be satisfied as asked.", {"component": COMPONENT}, ALL_ROLES)
def recommend_alternatives_tool(ctx: ToolContext, args: dict) -> dict:
    request = request_from_component(ctx, args["component"])
    return {"alternatives": [a.as_dict(ctx.index.snapshot) for a in recommend_alternatives(ctx.index, ctx.rules, request)]}


@tool("assess_disruption", "Impact of a closure on classes and bookings with conflict-free re-home proposals.", {
    "kind": {"type": "string", "enum": ["venue", "faculty", "lot"]}, "building_id": N, "venue_codes": STRINGS, "faculty_id": N, "lot_id": N, "start": ISO, "end": ISO, "description": S,
}, ADMIN)
def assess_disruption_tool(ctx: ToolContext, args: dict) -> dict:
    venue_ids = [venue_by_code(ctx, c) for c in args.get("venue_codes", [])]
    if args.get("building_id"):
        venue_ids += [v.id for v in ctx.index.snapshot.venues if v.building_id == int(args["building_id"])]
    closure = impact.Closure(args.get("kind", "venue"), parse_dt(args["start"], "start"), parse_dt(args["end"], "end"), venue_ids, args.get("faculty_id"), args.get("lot_id"), args.get("description", ""))
    limits = solver_settings()
    report = impact.assess(ctx.index, ctx.rules, closure, min(limits["time_limit"], 5), limits["workers"])
    return {"summary": {k: report[k] for k in ("kind", "affected", "resolved", "unresolved")}, "items": report["items"][:MAX_ITEMS], "full_report": report}


@tool("utilisation_report", "Utilisation KPIs for the last four weeks.", {"scope": S}, ADMIN)
def utilisation_report_tool(ctx: ToolContext, args: dict) -> dict:
    kpis = reports.monthly_kpis(ctx.session, ctx.now.date() - timedelta(days=28), ctx.now.date() - timedelta(days=1))
    return {k: kpis[k] for k in ("classroom_time_utilisation_pct", "seat_utilisation_pct", "peak_utilisation_pct", "off_peak_utilisation_pct", "ghost_classes", "ghost_bookable_hours_per_week", "by_type", "guest_house", "parking")}


@tool("detect_ghost_classes", "List timetabled classes whose telemetry shows they are rarely attended.", {}, ADMIN_APPROVER)
def detect_ghost_classes(ctx: ToolContext, args: dict) -> dict:
    report = ops.ghost_report(ctx.session)
    return {"count": len(report["ghosts"]), "projected_uplift_hours_per_week": report["projected_uplift_hours_per_week"], "ghosts": report["ghosts"][:MAX_ITEMS]}


@tool("search_policies", "Look up institutional policy text. Only the approved policy file is used.", {"query": S}, ALL_ROLES)
def search_policies(ctx: ToolContext, args: dict) -> dict:
    found = rag.retrieve(str(args["query"]))
    if not found:
        return {"found": False, "message": rag.REFUSAL, "rules": []}
    return {"found": True, "rules": [{"rule_id": c.rule_id, "text": c.text} for c, _ in found]}


@tool("explain", "Explain a booking or a venue window in plain words.", {"kind": {"type": "string", "enum": ["booking", "venue_window"]}, "booking_id": N, "venue_code": S, "start": ISO, "end": ISO}, ALL_ROLES)
def explain_tool(ctx: ToolContext, args: dict) -> dict:
    if args.get("kind") == "booking":
        return get_booking(ctx, {"booking_id": args["booking_id"]})
    return explain.explain_window(ctx.index, venue_by_code(ctx, args["venue_code"]), parse_dt(args["start"], "start"), parse_dt(args["end"], "end"), redact=ctx.redact)


@tool("get_booking", "Fetch one booking. Only the requester, sponsor or an administrator may see its details.", {"booking_id": N}, ALL_ROLES)
def get_booking(ctx: ToolContext, args: dict) -> dict:
    booking = ctx.session.get(t.Booking, int(args["booking_id"]))
    if booking is None:
        raise ToolError("No such booking")
    if not visible_to(ctx.user, booking):
        return {"error": "forbidden", "message": "You can only look at your own bookings."}
    return {"booking": booking_dict(ctx.session, booking, ctx.user)}


@tool("my_bookings", "List the signed-in user's bookings.", {}, ALL_ROLES)
def my_bookings(ctx: ToolContext, args: dict) -> dict:
    rows = ctx.session.exec(select(t.Booking).where(t.Booking.requester_id == ctx.user.id).order_by(t.Booking.start_dt)).all()
    return {"bookings": [{"id": b.id, "title": b.event_title, "status": b.status, "start": b.start_dt.isoformat(), "end": b.end_dt.isoformat()} for b in rows[:MAX_ITEMS]]}


@tool("plan_bundle", "Build and validate a booking proposal from one or more components. Nothing is stored; the human submits it.", {"title": S, "components": {"type": "array", "items": COMPONENT}, "external_speakers": N, "recording": {"type": "boolean"}, "sponsor_id": N}, ALL_ROLES, "propose")
def plan_bundle_tool(ctx: ToolContext, args: dict) -> dict:
    requests = [request_from_component(ctx, c, args.get("sponsor_id")) for c in args["components"]]
    if not requests:
        raise ToolError("Give at least one component")
    title = args.get("title") or requests[0].title or "Booking request"
    if len(requests) == 1:
        result = check_request(ctx.index, ctx.rules, requests[0])
        view = {"title": title, "ok": result.ok, "components": [{**trim_check(result), "resource_type": requests[0].resource_type, "start": requests[0].start.isoformat(), "end": requests[0].end.isoformat(), "label": label_for(ctx, requests[0])}], "bundle_violations": [], "suggestions": [], "alternatives": []}
        if not result.ok:
            view["alternatives"] = [a.as_dict(ctx.index.snapshot) for a in recommend_alternatives(ctx.index, ctx.rules, requests[0])]
        submit = {"endpoint": "/bookings", "body": component_body(requests[0])}
    else:
        proposal = plan_bundle(ctx.index, ctx.rules, title, requests, int(args.get("external_speakers", 0)), bool(args.get("recording")))
        view = proposal.as_dict(ctx.index)
        submit = {"endpoint": "/bundles", "body": {"title": title, "components": [component_body(r) for r in requests], "external_speakers": int(args.get("external_speakers", 0)), "recording": bool(args.get("recording"))}}
    ctx.proposals.append({"kind": "bundle" if len(requests) > 1 else "booking", "title": title, "ok": view["ok"], "view": view, "submit": submit, "requests": requests})
    return {"ok": view["ok"], "title": title, "components": [{"label": c.get("label"), "ok": c.get("ok"), "violations": c.get("violations", [])[:3], "conflicts": c.get("conflicts", [])[:2]} for c in view["components"]], "bundle_violations": view["bundle_violations"], "alternatives": len(view["alternatives"]), "suggestions": view["suggestions"]}


def label_for(ctx: ToolContext, request: BookingRequest) -> str:
    snapshot = ctx.index.snapshot
    if request.resource_type == "venue":
        return snapshot.venue(request.resource_id).code
    if request.resource_type == "guest_room":
        return next((r.code for r in snapshot.guest_rooms if r.id == request.resource_id), "")
    return next((l.name for l in snapshot.lots if l.id == request.resource_id), "")


@tool("propose_release", "Propose releasing one class occurrence so its room becomes bookable. Needs approval; nothing is changed.", {"entry_id": N, "course_code": S, "date": S, "reason": S}, STAFF, "propose")
def propose_release_tool(ctx: ToolContext, args: dict) -> dict:
    entry = None
    if args.get("entry_id"):
        entry = ctx.index.snapshot.entry(int(args["entry_id"]))
    elif args.get("course_code"):
        matches = [e for e in ctx.index.snapshot.entries if e.course_code == str(args["course_code"]).upper() and (ctx.user.role != "faculty" or e.faculty_id == ctx.user.ref_id)]
        entry = matches[0] if matches else None
    if entry is None:
        raise ToolError("No matching class found")
    day = date.fromisoformat(args["date"]) if args.get("date") else ctx.now.date() + timedelta(days=(entry.weekday - ctx.now.weekday()) % 7 or 7)
    venue = ctx.index.snapshot.venue(entry.venue_id)
    uplift = (entry.end_min - entry.start_min) / 60
    view = {"course": entry.course_code, "date": day.isoformat(), "venue": venue.code, "bookable_hours_freed": uplift}
    ctx.proposals.append({"kind": "release", "title": f"Release {entry.course_code} on {day:%d %b}", "ok": True, "view": view, "submit": {"endpoint": "/exceptions/propose-release", "body": {"entry_id": entry.id, "date": day.isoformat(), "reason": args.get("reason", "Class will not be held")}}, "requests": []})
    return view


@tool("propose_rehome", "Prepare a closure for the Disruption Center; assessment and re-home proposals are computed, nothing is changed.", {
    "kind": {"type": "string", "enum": ["venue", "faculty", "lot"]}, "building_id": N, "venue_codes": STRINGS, "faculty_id": N, "lot_id": N, "start": ISO, "end": ISO, "description": S,
}, ADMIN, "propose")
def propose_rehome_tool(ctx: ToolContext, args: dict) -> dict:
    result = assess_disruption_tool(ctx, args)
    body = {"kind": args.get("kind", "venue"), "description": args.get("description", ""), "start": args["start"], "end": args["end"], "venue_ids": [venue_by_code(ctx, c) for c in args.get("venue_codes", [])], "building_id": args.get("building_id"), "faculty_id": args.get("faculty_id"), "lot_id": args.get("lot_id")}
    ctx.proposals.append({"kind": "rehome", "title": args.get("description") or "Closure re-homing", "ok": result["summary"]["unresolved"] == 0, "view": result["full_report"], "submit": {"endpoint": "/disruptions/assess", "body": body}, "requests": []})
    return {"summary": result["summary"], "items": result["items"][:6]}


def tools_for(role: str) -> list[Tool]:
    return [tool_ for tool_ in TOOLS.values() if role in tool_.roles]


def declarations_for(role: str) -> list[dict]:
    return [{"name": x.name, "description": x.description, "parameters": x.parameters} for x in tools_for(role)]


def execute(ctx: ToolContext, name: str, args: dict) -> tuple[dict, float]:
    began = time.perf_counter()
    definition = TOOLS.get(name)
    if definition is None:
        return {"error": "unknown_tool", "message": f"There is no tool called {name}"}, 0.0
    if ctx.user.role not in definition.roles:
        outcome: dict = {"error": "forbidden", "message": f"Your role cannot use {name}"}
    else:
        try:
            outcome = definition.handler(ctx, args)
        except ToolError as error:
            outcome = {"error": "bad_request", "message": str(error)}
        except (KeyError, ValueError, TypeError) as error:
            outcome = {"error": "bad_request", "message": f"Invalid arguments: {error}"}
    return outcome, (time.perf_counter() - began) * 1000


def summarise_result(result: dict) -> str:
    if "error" in result:
        return f"{result['error']}: {result.get('message', '')}"[:160]
    keys = [k for k in ("free_count", "ok", "found", "count", "affected", "resolved", "plan") if k in result]
    if keys:
        return ", ".join(f"{k}={result[k] if k != 'plan' else len(result[k])}" for k in keys)[:160]
    return ", ".join(f"{k}" for k in list(result)[:5])


def audit_tool_call(ctx: ToolContext, name: str, args: dict, result: dict, latency_ms: float, model: str) -> None:
    audit.append(ctx.session, ctx.user.email, "agent.tool_call", {"tool": name, "args": args, "summary": summarise_result(result), "latency_ms": round(latency_ms, 1), "model": model, "denied": result.get("error") == "forbidden"})
