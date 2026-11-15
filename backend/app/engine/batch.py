import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ortools.sat.python import cp_model

from app.engine.availability import AvailabilityIndex
from app.engine.search import SearchRequest, search_free_rooms
from app.engine.timeutil import floor_slot
from app.engine.types import Snapshot
from app.rules import Rules

SATISFACTION_SCALE = 100


@dataclass
class Option:
    venue_id: int
    start: datetime
    end: datetime
    satisfaction: int
    capacity: int


@dataclass
class EventRequest:
    id: int
    title: str
    priority: int
    attendees: int
    options: list[Option] = field(default_factory=list)


@dataclass
class BatchResult:
    method: str
    chosen: dict[int, Option]
    accepted: int
    weighted_satisfaction: int
    capacity_waste: float
    runtime_ms: float
    status: str = "OK"

    def as_dict(self) -> dict:
        return {
            "method": self.method, "accepted": self.accepted, "weighted_satisfaction": self.weighted_satisfaction,
            "capacity_waste": round(self.capacity_waste, 3), "runtime_ms": round(self.runtime_ms, 1), "status": self.status,
            "assignments": [{"event_id": e, "venue_id": o.venue_id, "start": o.start.isoformat(), "end": o.end.isoformat()} for e, o in sorted(self.chosen.items())],
        }


def padded(snapshot: Snapshot, option: Option) -> tuple[datetime, datetime]:
    venue = snapshot.venue(option.venue_id)
    return option.start - timedelta(minutes=venue.setup_buffer_min), option.end + timedelta(minutes=venue.teardown_buffer_min)


def conflicts(snapshot: Snapshot, a: Option, b: Option) -> bool:
    if a.venue_id != b.venue_id:
        return False
    a_start, a_end = padded(snapshot, a)
    b_start, b_end = padded(snapshot, b)
    return a_start < b_end and b_start < a_end


def summarise(method: str, events: dict[int, EventRequest], chosen: dict[int, Option], runtime_ms: float, status: str = "OK") -> BatchResult:
    satisfaction = sum(events[e].priority * o.satisfaction for e, o in chosen.items())
    waste = sum((o.capacity - events[e].attendees) / o.capacity for e, o in chosen.items()) / len(chosen) if chosen else 0.0
    return BatchResult(method, chosen, len(chosen), satisfaction, waste, runtime_ms, status)


def greedy_first_come(snapshot: Snapshot, events: list[EventRequest]) -> BatchResult:
    began = time.perf_counter()
    chosen: dict[int, Option] = {}
    for event in events:
        for option in sorted(event.options, key=lambda o: -o.satisfaction):
            if not any(conflicts(snapshot, option, taken) for taken in chosen.values()):
                chosen[event.id] = option
                break
    return summarise("greedy_fcfs", {e.id: e for e in events}, chosen, (time.perf_counter() - began) * 1000)


def optimise(snapshot: Snapshot, events: list[EventRequest], time_limit: float, workers: int) -> BatchResult:
    began = time.perf_counter()
    model = cp_model.CpModel()
    pick: dict[tuple[int, int], cp_model.IntVar] = {}
    for event in events:
        for number, _ in enumerate(event.options):
            pick[event.id, number] = model.NewBoolVar(f"e{event.id}_o{number}")
        model.AddAtMostOne(pick[event.id, number] for number in range(len(event.options)))
    cover: dict[tuple[int, date, int], list[cp_model.IntVar]] = defaultdict(list)
    for event in events:
        for number, option in enumerate(event.options):
            low, high = padded(snapshot, option)
            slot = low
            while slot < high:
                cover[option.venue_id, slot.date(), floor_slot(slot.hour * 60 + slot.minute)].append(pick[event.id, number])
                slot += timedelta(minutes=15)
    for variables in cover.values():
        if len(variables) > 1:
            model.AddAtMostOne(variables)
    by_id = {e.id: e for e in events}
    objective = []
    for event in events:
        for number, option in enumerate(event.options):
            waste_penalty = int((option.capacity - event.attendees) * 10 / max(1, option.capacity))
            objective.append((event.priority * (1000 + option.satisfaction) - waste_penalty) * pick[event.id, number])
    model.Maximize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    status = solver.Solve(model)
    chosen: dict[int, Option] = {}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (event_id, number), variable in pick.items():
            if solver.Value(variable):
                chosen[event_id] = by_id[event_id].options[number]
    label = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE"}.get(status, "NO_SOLUTION")
    return summarise("cp_sat", by_id, chosen, (time.perf_counter() - began) * 1000, label)


def build_events(index: AvailabilityIndex, rules: Rules, count: int, seed: int, first_day: date, days: int = 5) -> list[EventRequest]:
    generator = random.Random(seed)
    events: list[EventRequest] = []
    for number in range(1, count + 1):
        attendees = generator.choice([60, 80, 120, 150, 200, 280, 350, 500])
        day = first_day + timedelta(days=generator.randrange(days))
        preferred_hour = generator.choice([10, 11, 14, 15, 16, 17])
        length = generator.choice([60, 90, 120])
        event = EventRequest(number, f"Fest event {number}", generator.choice([1, 2, 3, 4, 5]), attendees)
        types = ["amphitheatre", "seminar_hall", "classroom"]
        for shift_hours in (0, 1, -1, 2, -2):
            start = datetime(day.year, day.month, day.day, max(8, min(19, preferred_hour + shift_hours)))
            end = start + timedelta(minutes=length)
            outcome = search_free_rooms(index, SearchRequest(windows=[(start, end)], attendees=attendees, types=types), rules)
            for hit in outcome.hits[:4]:
                event.options.append(Option(hit.venue.id, start, end, max(10, 100 - abs(shift_hours) * 15 - int((1 - hit.score / 100) * 20)), hit.venue.capacity))
        events.append(event)
    return events


def compare(index: AvailabilityIndex, rules: Rules, events: list[EventRequest], time_limit: float, workers: int) -> dict:
    snapshot = index.snapshot
    greedy = greedy_first_come(snapshot, events)
    optimal = optimise(snapshot, events, time_limit, workers)
    return {"events": len(events), "greedy": greedy.as_dict(), "cp_sat": optimal.as_dict()}
