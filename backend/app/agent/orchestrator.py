import dataclasses
import json
from collections.abc import Generator, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlmodel import select

from app import db
from app.agent import compose, prompts, rag, tools
from app.agent.fallback_parser import Intent, is_injection, parse
from app.agent.llm import LLMUnavailable, get_llm
from app.agent.narrative import numbers_verified
from app.engine import validator
from app.engine.proposal import check_request
from app.engine.types import BookingInfo
from app.models import tables as t
from app.services import audit

MAX_TOOLS = 6
MAX_LLM_TURNS = 3
UNKNOWN_OPTIONS = ["Find a free classroom tomorrow 2-4 pm for 60", "Book lab L-3 on 20 Nov 10 to 1", "Parking for 15 cars on 4 Dec", "What is the lead time for an amphitheatre?"]
REFUSAL_TEXT = "I can't act on instructions that try to change my rules, skip approvals or reveal my setup. I can still help you find rooms, plan bookings or answer policy questions."


@dataclass
class Call:
    name: str
    args: dict
    rationale: str


@dataclass
class Outcome:
    answer: str = ""
    clarify: dict | None = None
    facts: list[dict] = field(default_factory=list)


Script = Generator[Call, dict, Outcome]


def clarify_event(question: str, options: list[str], field_name: str) -> dict:
    return {"type": "clarify", "question": question, "options": options, "field": field_name}


def iso(day: date, minute: int) -> str:
    return (datetime(day.year, day.month, day.day) + timedelta(minutes=minute)).isoformat()


def date_options(now: datetime) -> list[str]:
    days = [now.date() + timedelta(days=n) for n in range(1, 8) if (now.date() + timedelta(days=n)).weekday() < 6][:4]
    return [f"on {d.day} {d:%b}" for d in days]


def plan_call(steps: list[str], rationale: str) -> Call:
    return Call("declare_plan", {"steps": steps, "rationale": rationale}, "Write down the plan before touching any data")


def need_window(params: dict, now: datetime, default_minutes: int = 60) -> tuple[tuple[date, int, int] | None, dict | None]:
    if not params["dates"]:
        return None, clarify_event("Which date do you need it on?", date_options(now), "date")
    if params["start_min"] is None:
        return None, clarify_event("What time should it run?", ["9-10 am", "10-11 am", "2-4 pm", "4-6 pm"], "time")
    end = params["end_min"] or params["start_min"] + (params["duration_min"] or default_minutes)
    return (params["dates"][0], params["start_min"], end), None


def sponsor_options(ctx: tools.ToolContext) -> list[str]:
    users = ctx.session.exec(select(t.User).where(t.User.role == "faculty")).all()
    return [f"sponsored by {u.name}" for u in users[:4]]


def sponsor_from(ctx: tools.ToolContext, text: str) -> int | None:
    for user in ctx.session.exec(select(t.User).where(t.User.role == "faculty")):
        if user.name and user.name in text:
            return user.id
    return None


def venue_args(window: tuple[date, int, int], params: dict, types: list[str]) -> dict:
    day, start, end = window
    return {"start": iso(day, start), "end": iso(day, end), "attendees": params["attendees"] or 0, "types": types, "building_id": params.get("building_id")}


def script_free_rooms(intent: Intent, ctx: tools.ToolContext) -> Script:
    window, ask = need_window(intent.params, ctx.now)
    if ask:
        return Outcome(clarify=ask)
    types = [intent.params["venue_type"]] if intent.params["venue_type"] else ["classroom", "seminar_hall"]
    yield plan_call(["Read the date, time and size", "Search every room and keep the free ones", "Rank them and explain the rest"], "Free rooms are computed from timetables, bookings, holds and maintenance")
    result = yield Call("search_free_rooms", venue_args(window, intent.params, types), "Check each room for the whole window")
    return Outcome(compose.free_rooms(result) if "hits" in result else result.get("message", "I could not search that window."), facts=[result])


def script_book_venue(intent: Intent, ctx: tools.ToolContext) -> Script:
    params = intent.params
    window, ask = need_window(params, ctx.now, 120)
    if ask:
        return Outcome(clarify=ask)
    if params["venue_type"] == "amphitheatre" and not params["attendees"] and not params["venue_code"]:
        return Outcome(clarify=clarify_event("How many people will attend?", ["for 100 people", "for 250 people", "for 500 people"], "attendees"))
    sponsor = sponsor_from(ctx, intent.original)
    if ctx.user.role == "student" and sponsor is None:
        return Outcome(clarify=clarify_event("Students need a faculty sponsor. Who will sponsor this?", sponsor_options(ctx), "sponsor"))
    yield plan_call(["Pick the room", "Check policy and availability", "Prepare a proposal or ranked alternatives"], "A proposal is only valid if both the policy engine and the validator accept it")
    code = params["venue_code"]
    facts: list[dict] = []
    if not code:
        types = [params["venue_type"] or "classroom"]
        search = yield Call("search_free_rooms", venue_args(window, params, types), "Find the best-fitting free room")
        facts.append(search)
        if search.get("hits"):
            code = search["hits"][0]["code"]
        else:
            fallback = next(v for v in ctx.index.snapshot.venues if v.type == types[0] and v.capacity >= (params["attendees"] or 0))
            code = fallback.code
    day, start, end = window
    component = {"resource_type": "venue", "resource_code": code, "start": iso(day, start), "end": iso(day, end), "attendees": params["attendees"] or 0, "title": params["title"] or "Booking request"}
    plan = yield Call("plan_bundle", {"title": params["title"] or f"Booking of {code}", "components": [component], "sponsor_id": sponsor}, "Validate the exact room and time")
    facts.append(plan)
    note = "" if params["attendees"] else "You did not give an attendee count, so capacity was not checked."
    return Outcome(compose.booking_outcome(plan, note) if "components" in plan else plan.get("message", "I could not prepare that proposal."), facts=facts)


def script_bundle(intent: Intent, ctx: tools.ToolContext) -> Script:
    params = intent.params
    if not params["dates"]:
        return Outcome(clarify=clarify_event("Which dates is the event on?", date_options(ctx.now), "date"))
    if not params["attendees"]:
        return Outcome(clarify=clarify_event("How many people will attend?", ["for 50 people", "for 80 people", "for 150 people"], "attendees"))
    sponsor = sponsor_from(ctx, intent.original)
    if ctx.user.role == "student" and sponsor is None:
        return Outcome(clarify=clarify_event("Students need a faculty sponsor. Who will sponsor this?", sponsor_options(ctx), "sponsor"))
    first = params["dates"][0]
    last = params["dates"][-1] if len(params["dates"]) > 1 else first + timedelta(days=(params["event_days"] or 1) - 1)
    days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    start_min = params["start_min"] if params["start_min"] is not None else 600
    end_min = params["end_min"] or start_min + 360
    hall_type = "amphitheatre" if end_min - start_min > 240 else "seminar_hall"
    title = params["title"] or "Campus event"
    yield plan_call(["Pick a hall that fits the headcount", "Find guest house rooms for speakers", "Plan visitor parking near the hall", "Validate everything together"], "One sentence becomes a venue, guest house and parking bundle that is held and confirmed together")
    search = yield Call("search_free_rooms", venue_args((first, start_min, end_min), params, [hall_type]), f"Find a free {hall_type.replace('_', ' ')} for the first day")
    facts = [search]
    if not search.get("hits"):
        return Outcome(compose.free_rooms(search) if "window" in search else "No hall is free then.", facts=facts)
    hall = search["hits"][0]["code"]
    components = [{"resource_type": "venue", "resource_code": hall, "start": iso(day, start_min), "end": iso(day, end_min), "attendees": params["attendees"], "title": f"{title} day {n}"} for n, day in enumerate(days, start=1)]
    if params["speakers"] or params["nights"]:
        guests = params["speakers"] or 1
        nights = params["nights"] or len(days) + 1
        arrival = first - timedelta(days=1)
        rooms = yield Call("check_guesthouse", {"start": iso(arrival, 14 * 60), "end": iso(arrival + timedelta(days=nights), 11 * 60), "guests": 1, "category": "official"}, "Find single rooms for the external speakers")
        facts.append(rooms)
        for room in rooms.get("rooms", [])[:guests]:
            components.append({"resource_type": "guest_room", "resource_code": room["code"], "start": iso(arrival, 14 * 60), "end": iso(arrival + timedelta(days=nights), 11 * 60), "attendees": 1, "title": "Speaker room", "meta": {"guests": 1, "category": "official"}, "host_ref": title})
    if params["cars"]:
        parked = yield Call("check_parking", {"start": iso(first, 9 * 60), "end": iso(last, 18 * 60), "vehicles": {"car": params["cars"]}, "near_venue_code": hall}, "Pick the closest lots with free capacity")
        facts.append(parked)
        for allocation in parked.get("allocations", []):
            components.append({"resource_type": "parking", "resource_code": allocation["lot"], "start": iso(first, 9 * 60), "end": iso(last, 18 * 60), "attendees": params["attendees"], "qty": sum(allocation["vehicles"].values()), "title": "Visitor parking", "meta": {"vehicles": allocation["vehicles"]}})
    plan = yield Call("plan_bundle", {"title": title, "components": components, "external_speakers": params["speakers"] or 0, "recording": params["recording"], "sponsor_id": sponsor}, "Check every component and the rules that tie them together")
    facts.append(plan)
    return Outcome(compose.booking_outcome(plan) if "components" in plan else plan.get("message", "I could not prepare that bundle."), facts=facts)


def script_cohort(intent: Intent, ctx: tools.ToolContext) -> Script:
    params = intent.params
    if not params.get("semester"):
        return Outcome(clarify=clarify_event("Which semester?", ["for Sem 1", "for Sem 3", "for Sem 5", "for Sem 7"], "semester"))
    dates = params["dates"] or [ctx.now.date() + timedelta(days=n) for n in range(1, 8)]
    duration = params["duration_min"] or 60
    sponsor = sponsor_from(ctx, intent.original)
    yield plan_call(["Collect the timetables of every section", "Intersect their free time", "Pick a room and prepare a proposal"], "Common free time is the AND of every section's free bit-array")
    search = yield Call("find_common_free_slots", {"dept": params.get("dept"), "semester": params["semester"], "section_names": params.get("section_names"), "start_date": dates[0].isoformat(), "end_date": dates[-1].isoformat(), "duration_min": duration, "earliest": "09:00", "latest": "18:00"}, "Rank slots by least disruption")
    facts = [search]
    if search.get("error") or not search.get("slots"):
        return Outcome(compose.cohort(search, None) if "slots" in search else search.get("message", "No sections matched."), facts=facts)
    best = search["slots"][0]
    kind = "Quiz" if "quiz" in intent.original.lower() else "Extra lecture"
    component = {"resource_type": "venue", "resource_code": best["rooms"][0]["code"], "start": best["start"], "end": best["end"], "attendees": search["attendees"], "title": f"{kind}: {', '.join(search['section_labels'])}"}
    plan = yield Call("plan_bundle", {"title": component["title"], "components": [component], "sponsor_id": sponsor}, "Turn the best slot into a checked proposal")
    facts.append(plan)
    return Outcome(compose.cohort(search, plan), facts=facts)


def script_guest_room(intent: Intent, ctx: tools.ToolContext) -> Script:
    params = intent.params
    if not params["dates"]:
        return Outcome(clarify=clarify_event("Which day is check-in?", date_options(ctx.now), "date"))
    nights = params["nights"] or 1
    guests = params["speakers"] or 1
    arrival = params["dates"][0]
    yield plan_call(["Find rooms free for the nights", "Pick the best fit", "Prepare a proposal linked to a host"], "Guest nights need a host and a turnover buffer")
    rooms = yield Call("check_guesthouse", {"start": iso(arrival, 14 * 60), "end": iso(arrival + timedelta(days=nights), 11 * 60), "guests": guests, "category": "other"}, "List free rooms best fit first")
    facts = [rooms]
    if not rooms.get("rooms"):
        return Outcome(compose.guest_rooms(rooms) if "rooms" in rooms else rooms.get("message", ""), facts=facts)
    component = {"resource_type": "guest_room", "resource_code": rooms["rooms"][0]["code"], "start": iso(arrival, 14 * 60), "end": iso(arrival + timedelta(days=nights), 11 * 60), "attendees": guests, "title": "Guest stay", "meta": {"guests": guests}, "host_ref": f"Host: {ctx.user.name or ctx.user.email}"}
    plan = yield Call("plan_bundle", {"title": "Guest house stay", "components": [component]}, "Validate the stay against policy")
    facts.append(plan)
    return Outcome(compose.guest_rooms(rooms) + " " + compose.proposal_sentence(plan), facts=facts)


def script_parking(intent: Intent, ctx: tools.ToolContext) -> Script:
    params = intent.params
    if not params["dates"]:
        return Outcome(clarify=clarify_event("Which date is the parking for?", date_options(ctx.now), "date"))
    day = params["dates"][0]
    start = params["start_min"] if params["start_min"] is not None else 9 * 60
    end = params["end_min"] or 18 * 60
    vehicles = {k: v for k, v in {"car": params["cars"], "bike": params["bikes"], "bus": params["buses"]}.items() if v}
    if not vehicles:
        return Outcome(clarify=clarify_event("How many vehicles?", ["10 cars", "25 cars", "2 buses"], "vehicles"))
    yield plan_call(["Check lot capacity with the walk-in reserve", "Choose lots by distance", "Prepare a proposal"], "Parking capacity is a per-lot, per-vehicle-type timeline")
    plan_result = yield Call("check_parking", {"start": iso(day, start), "end": iso(day, end), "vehicles": vehicles, "near_venue_code": params["venue_code"]}, "Fit the vehicles into lots")
    facts = [plan_result]
    if not plan_result.get("ok"):
        return Outcome(compose.parking(plan_result), facts=facts)
    total = sum(vehicles.values())
    components = [{"resource_type": "parking", "resource_code": a["lot"], "start": iso(day, start), "end": iso(day, end), "attendees": total, "qty": sum(a["vehicles"].values()), "title": "Visitor parking", "meta": {"vehicles": a["vehicles"]}} for a in plan_result["allocations"]]
    plan = yield Call("plan_bundle", {"title": "Visitor parking", "components": components}, "Validate against parking rules")
    facts.append(plan)
    return Outcome(compose.parking(plan_result) + " " + compose.proposal_sentence(plan), facts=facts)


def script_closure(intent: Intent, ctx: tools.ToolContext) -> Script:
    params = intent.params
    if ctx.user.role != "admin":
        return Outcome("Only administrators can assess a closure and re-home classes.")
    if not params["dates"]:
        return Outcome(clarify=clarify_event("Which days is it closed?", date_options(ctx.now), "date"))
    if not params["building_id"] and not params["venue_code"]:
        return Outcome(clarify=clarify_event("Which building or venue is closed?", [b.name for b in ctx.index.snapshot.buildings.values()][:6], "building"))
    yield plan_call(["Find every class and booking in the closed place", "Search conflict-free alternatives with the solver", "Prepare re-home proposals for approval"], "Re-homing is solved globally so no two moved items collide")
    args: dict = {"kind": "venue", "start": iso(params["dates"][0], 0), "end": iso(params["dates"][-1] + timedelta(days=1), 0), "description": intent.original}
    if params["building_id"]:
        args["building_id"] = params["building_id"]
    else:
        args["venue_codes"] = [params["venue_code"]]
    result = yield Call("propose_rehome", args, "Compute impact and a conflict-free re-home plan")
    return Outcome(compose.closure(result) if "summary" in result else result.get("message", ""), facts=[result])


def script_release(intent: Intent, ctx: tools.ToolContext) -> Script:
    if not intent.params["course_code"]:
        return Outcome(clarify=clarify_event("Which course code should be released?", ["release CS501", "release CS502"], "course"))
    yield plan_call(["Find the class", "Prepare a release proposal"], "Releasing a slot needs approval from the head of department")
    args = {"course_code": intent.params["course_code"], "reason": "Class will not be held"}
    if intent.params["dates"]:
        args["date"] = intent.params["dates"][0].isoformat()
    result = yield Call("propose_release", args, "Prepare the release without changing anything")
    return Outcome(compose.release(result) if "course" in result else result.get("message", ""), facts=[result])


def script_simple(tool_name: str, composer: Any, steps: list[str]) -> Any:
    def script(intent: Intent, ctx: tools.ToolContext) -> Script:
        yield plan_call(steps, "Read-only lookup")
        result = yield Call(tool_name, {}, "Read the data")
        return Outcome(composer(result) if "error" not in result else result["message"], facts=[result])

    return script


def script_lookup(intent: Intent, ctx: tools.ToolContext) -> Script:
    yield plan_call(["Look up the booking", "Check that you may see it"], "Booking details are private to the requester, sponsor and administrators")
    if intent.params["booking_id"]:
        result = yield Call("get_booking", {"booking_id": intent.params["booking_id"]}, "Fetch the booking with an access check")
        return Outcome(compose.lookup(result) if "error" not in result or result["error"] == "forbidden" else result["message"], facts=[result])
    result = yield Call("my_bookings", {}, "List your own bookings")
    return Outcome(compose.my_bookings(result), facts=[result])


def script_policy(intent: Intent, ctx: tools.ToolContext) -> Script:
    yield plan_call(["Search the approved policies", "Answer only from the retrieved rules"], "Policy answers come only from the approved policy file")
    result = yield Call("search_policies", {"query": intent.params["question"]}, "Retrieve the matching rules")
    answer = rag.ask_policy(intent.params["question"], use_llm=get_llm().usable())
    return Outcome(answer["answer"] + ("" if answer["refused"] else ""), facts=[result, {"policy_answer": answer}])


SCRIPTS = {
    "free_rooms": script_free_rooms, "book_venue": script_book_venue, "bundle": script_bundle, "cohort": script_cohort, "guest_room": script_guest_room,
    "parking": script_parking, "closure": script_closure, "release": script_release, "lookup": script_lookup, "policy": script_policy,
    "ghost": script_simple("detect_ghost_classes", compose.ghosts, ["Compare telemetry with the timetable", "List flagged classes"]),
    "utilisation": script_simple("utilisation_report", compose.utilisation, ["Compute utilisation from the live index", "Summarise"]),
}


def log(email: str, action: str, detail: dict) -> None:
    with db.session_scope(write=True) as session:
        audit.append(session, email, action, detail)
        session.commit()


def verify_proposal(ctx: tools.ToolContext, proposal: dict) -> dict:
    requests = proposal.get("requests", [])
    if not requests:
        return {"policy": {"ok": True, "violations": []}, "validator": {"ok": True, "violations": []}}
    policy_violations: list[dict] = []
    for request in requests:
        policy_violations += [v.as_dict() for v in check_request(ctx.index, ctx.rules, request).hard]
    snapshot = ctx.index.snapshot
    probes = [
        BookingInfo(id=-(n + 1), bundle_id=None, resource_type=r.resource_type, resource_id=r.resource_id, qty=r.qty, requester_id=0, event_title="proposal", attendees=r.attendees, start_dt=r.start, end_dt=r.end, priority_class=4, status="CONFIRMED", hold_expires_at=None, meta={k: v for k, v in r.meta.items() if k != "exclude_booking_id"})
        for n, r in enumerate(requests)
    ]
    probe = dataclasses.replace(snapshot, bookings=snapshot.bookings + probes)
    found = validator.validate(probe, ctx.rules, {(r.resource_type, r.resource_id) for r in requests})
    return {"policy": {"ok": not policy_violations, "violations": policy_violations}, "validator": {"ok": not found, "violations": [v.as_dict() for v in found]}}


def public_proposal(proposal: dict, verification: dict) -> dict:
    ok = proposal["ok"] and verification["policy"]["ok"] and verification["validator"]["ok"]
    return {"kind": proposal["kind"], "title": proposal["title"], "ok": ok, "view": proposal["view"], "submit": proposal["submit"], "verification": verification}


class Agent:
    def __init__(self, ctx: tools.ToolContext, message: str) -> None:
        self.ctx = ctx
        self.message = message
        self.llm = get_llm()
        self.llm_calls = 0
        self.tool_count = 0
        self.plan_steps = 0
        self.progress = 0
        self.model = "offline"

    def emit(self, event: dict) -> dict:
        if event["type"] not in ("answer_delta",):
            log(self.ctx.user.email, f"agent.{event['type']}", {k: v for k, v in event.items() if k != "type"} | {"message": self.message[:300]})
        return event

    def execute(self, name: str, args: dict, rationale: str) -> Generator[dict, None, dict]:
        self.tool_count += 1
        call_id = self.tool_count
        yield self.emit({"type": "tool_call", "id": call_id, "name": name, "args": args, "rationale": rationale})
        outcome, latency = tools.execute(self.ctx, name, args)
        yield self.emit({"type": "tool_result", "id": call_id, "name": name, "summary": tools.summarise_result(outcome), "latency_ms": round(latency, 1), "error": "error" in outcome})
        if name == "declare_plan":
            self.plan_steps = len(outcome.get("plan", []))
            yield self.emit({"type": "plan", "steps": outcome.get("plan", []), "rationale": outcome.get("rationale", "")})
        else:
            self.progress += 1
            yield self.emit({"type": "plan_progress", "done": min(self.progress, self.plan_steps)})
        return outcome

    def run_script(self, intent: Intent) -> Generator[dict, None, Outcome]:
        script = SCRIPTS[intent.kind](intent, self.ctx)
        try:
            call = next(script)
            while True:
                if self.tool_count >= MAX_TOOLS:
                    return Outcome("I stopped because the request needed too many steps. Please ask for one thing at a time.")
                result = yield from self.execute(call.name, call.args, call.rationale)
                call = script.send(result)
        except StopIteration as stop:
            return stop.value

    def run_llm_loop(self) -> Generator[dict, None, str | None]:
        from google.genai import types

        contents: list[Any] = [types.Content(role="user", parts=[types.Part(text=prompts.user_turn(self.ctx, self.message))])]
        declarations = tools.declarations_for(self.ctx.user.role)
        for turn in range(MAX_LLM_TURNS):
            try:
                result = self.llm.generate(contents, system=prompts.SYSTEM, tools=declarations, force_tool=turn == 0)
            except LLMUnavailable:
                return None
            self.llm_calls += 1
            self.model = result.model
            if not result.tool_calls:
                return result.text or None
            contents.append(types.Content(role="model", parts=result.parts))
            responses = []
            for requested in result.tool_calls:
                if self.tool_count >= MAX_TOOLS:
                    break
                outcome = yield from self.execute(requested.name, requested.args, "Chosen by the model for this request")
                responses.append(types.Part.from_function_response(name=requested.name, response={"result": json.loads(json.dumps({k: v for k, v in outcome.items() if k != "full_report"}, default=str))}))
            contents.append(types.Content(role="user", parts=responses))
        return None

    def stream_answer(self, outcome: Outcome) -> Iterator[str]:
        if outcome.facts and self.llm.usable() and not any("policy_answer" in f for f in outcome.facts) and self.llm_calls < 4:
            payload = [{k: v for k, v in f.items() if k != "full_report"} for f in outcome.facts]
            try:
                pieces: list[str] = []
                self.llm_calls += 1
                for chunk in self.llm.stream_text(prompts.answer_prompt(self.message, payload)):
                    pieces.append(chunk)
                text = "".join(pieces).strip()
                if text and numbers_verified(text, payload, self.message + outcome.answer):
                    self.model = self.llm.settings.gemini_model
                    yield from (p for p in pieces)
                    return
            except LLMUnavailable:
                pass
        words = outcome.answer.split(" ")
        for start in range(0, len(words), 6):
            yield " ".join(words[start:start + 6]) + (" " if start + 6 < len(words) else "")

    def run(self) -> Iterator[dict]:
        status = self.llm.status()
        yield self.emit({"type": "start", "mode": status["mode"], "role": self.ctx.user.role})
        intent = parse(self.message, self.ctx.now, {v.code for v in self.ctx.index.snapshot.venues}, {b.id: b.name for b in self.ctx.index.snapshot.buildings.values()})
        outcome: Outcome | None = None
        if intent.kind == "injection" or is_injection(self.message):
            outcome = Outcome(REFUSAL_TEXT)
            yield self.emit({"type": "refusal", "reason": "prompt-injection pattern ignored"})
        elif intent.kind == "unknown":
            if self.llm.usable():
                text = yield from self.run_llm_loop()
                if text:
                    outcome = Outcome(text)
            if outcome is None:
                outcome = Outcome(clarify=clarify_event("I can help with rooms, bookings, events and policies. What would you like to do?", UNKNOWN_OPTIONS, "intent"))
        else:
            outcome = yield from self.run_script(intent)
        if outcome.clarify:
            yield self.emit(outcome.clarify)
            yield self.emit({"type": "done", "mode": status["mode"], "llm_calls": self.llm_calls, "tool_calls": self.tool_count})
            return
        for proposal in self.ctx.proposals:
            verification = verify_proposal(self.ctx, proposal)
            yield self.emit({"type": "verify", **verification})
            public = public_proposal(proposal, verification)
            if not public["ok"] and proposal["ok"]:
                outcome.answer = "I prepared a proposal, but verification found a problem: " + "; ".join(v["message"] for v in verification["policy"]["violations"] + verification["validator"]["violations"])[:300]
            yield self.emit({"type": "proposal", "proposal": public})
        for chunk in self.stream_answer(outcome):
            yield {"type": "answer_delta", "text": chunk}
        log(self.ctx.user.email, "agent.answer", {"text": outcome.answer[:500], "llm_calls": self.llm_calls, "tool_calls": self.tool_count})
        yield self.emit({"type": "done", "mode": self.llm.status()["mode"], "llm_calls": self.llm_calls, "tool_calls": self.tool_count})
