import math
import random
from datetime import date, datetime, timedelta

from app.rules import load_rules

SEED = 42
TERM_START = date(2026, 8, 3)
TERM_END = date(2026, 12, 5)
HOLIDAYS = [(date(2026, 10, 20), "Synthetic Autumn Holiday"), (date(2026, 11, 24), "Synthetic Founders Day Holiday")]
DEPTS = ["CSE", "ECE", "ME", "CHE", "EEE"]
SEMESTERS = [1, 3, 5, 7]
SECTION_NAMES = ["A", "B"]
CLASSROOM_CAPACITIES = [120] * 2 + [100] * 3 + [90] * 3 + [80] * 5 + [70] * 6 + [60] * 7 + [50] * 5 + [40] * 3

BUILDINGS = [
    (1, "Academic Block A", 200, 300, "academic"),
    (2, "Academic Block B", 320, 300, "academic"),
    (3, "Academic Block C", 440, 300, "academic"),
    (4, "Library", 320, 200, "academic"),
    (5, "Admin Block", 320, 100, "admin"),
    (6, "Lab Complex 1", 200, 450, "labs"),
    (7, "Lab Complex 2", 440, 450, "labs"),
    (8, "Amphitheatre Complex", 320, 520, "events"),
    (9, "MDC Guest House", 580, 120, "residential"),
    (10, "Sports Complex", 580, 420, "sports"),
]

LAB_PLAN = [
    ("cs", 4, 6, ["CSE", "ECE", "EEE"], False),
    ("electronics", 3, 6, ["ECE", "EEE", "CSE"], True),
    ("physics", 2, 6, DEPTS, False),
    ("chem", 2, 7, ["CHE", "ME"], True),
    ("mech", 3, 7, ["ME", "CHE", "EEE"], True),
]

DEPT_LABS = {
    "CSE": ["cs", "cs"],
    "ECE": ["electronics", "cs"],
    "ME": ["mech", "physics"],
    "CHE": ["chem", "physics"],
    "EEE": ["electronics", "physics"],
}

COURSE_TOPICS = {
    "CSE": ["Programming Fundamentals", "Discrete Mathematics", "Data Structures", "Digital Logic", "Computer Organisation", "Algorithms", "Operating Systems", "Database Systems", "Computer Networks", "Software Engineering", "Theory of Computation", "Compiler Design", "Machine Learning", "Distributed Systems", "Information Security", "Cloud Computing", "Deep Learning", "Big Data Analytics", "Natural Language Processing", "Capstone Seminar"],
    "ECE": ["Circuit Analysis", "Signals and Systems", "Analog Electronics", "Digital Electronics", "Electromagnetic Theory", "Communication Systems", "Microprocessors", "Control Systems", "Digital Signal Processing", "VLSI Design", "Antenna Theory", "Embedded Systems", "Wireless Networks", "Optical Communication", "Radar Systems", "Image Processing", "IoT Systems", "Satellite Communication", "RF Design", "Capstone Seminar"],
    "ME": ["Engineering Mechanics", "Thermodynamics", "Fluid Mechanics", "Material Science", "Machine Drawing", "Heat Transfer", "Manufacturing Processes", "Kinematics of Machines", "Machine Design", "Dynamics of Machinery", "Refrigeration", "Metrology", "CAD CAM", "Power Plant Engineering", "Robotics", "Finite Element Methods", "Automobile Engineering", "Operations Research", "Mechatronics", "Capstone Seminar"],
    "CHE": ["Chemical Process Principles", "Organic Chemistry", "Fluid Flow Operations", "Chemical Thermodynamics", "Heat Transfer Operations", "Mass Transfer", "Reaction Engineering", "Process Control", "Transport Phenomena", "Process Design", "Petroleum Refining", "Polymer Science", "Biochemical Engineering", "Environmental Engineering", "Process Safety", "Catalysis", "Nanomaterials", "Energy Systems", "Plant Design", "Capstone Seminar"],
    "EEE": ["Electrical Circuits", "Electromagnetic Fields", "Electrical Machines", "Power Systems", "Analog Circuits", "Control Engineering", "Power Electronics", "Measurements", "Switchgear", "Electric Drives", "Renewable Energy", "Smart Grids", "High Voltage", "Energy Management", "Instrumentation", "Embedded Control", "Power Quality", "Electric Vehicles", "Protection Systems", "Capstone Seminar"],
}

FIRST_INITIALS = ["A", "B", "C", "D", "G", "H", "K", "M", "N", "P", "R", "S", "T", "V"]
SURNAMES = ["Rao", "Mehta", "Iyer", "Singh", "Nair", "Kapoor", "Verma", "Joshi", "Bose", "Menon", "Das", "Khan", "Reddy", "Shah", "Pillai", "Sinha", "Gill", "Bhat", "Saxena", "Roy"]
DEPT_PREFIX = {"CSE": "CS", "ECE": "EC", "ME": "ME", "CHE": "CH", "EEE": "EE"}

PERIODS = load_rules().periods
PERIOD_COUNT = len(PERIODS)


def hhmm_to_min(text: str) -> int:
    hours, minutes = text.split(":")
    return int(hours) * 60 + int(minutes)


def period_bounds(start_period: int, span: int) -> tuple[int, int]:
    return hhmm_to_min(PERIODS[start_period][0]), hhmm_to_min(PERIODS[start_period + span - 1][1])


def periods_on_day(weekday: int) -> int:
    return 4 if weekday == 5 else PERIOD_COUNT


def start_periods(weekday: int, span: int) -> list[int]:
    allowed = periods_on_day(weekday)
    morning = [p for p in range(0, 4 - span + 1) if p + span <= min(4, allowed)]
    afternoon = [p for p in range(4, PERIOD_COUNT - span + 1) if p + span <= allowed]
    return morning + afternoon


def build_buildings() -> list[dict]:
    return [{"id": i, "name": n, "x": x, "y": y, "zone": z} for i, n, x, y, z in BUILDINGS]


def build_venues() -> list[dict]:
    rules = load_rules()
    venues: list[dict] = []

    def add(code: str, name: str, vtype: str, building: int, floor: int, capacity: int, features: list[str], **extra) -> None:
        rule = rules.for_venue_type(vtype)
        venues.append({
            "id": len(venues) + 1, "code": code, "name": name, "type": vtype, "building_id": building, "floor": floor,
            "capacity": capacity, "features": features, "lab_type": extra.get("lab_type"),
            "eligible_depts": extra.get("eligible_depts", []), "needs_supervisor": extra.get("needs_supervisor", False),
            "accessible": floor == 0 or extra.get("accessible", False), "bookable": True,
            "setup_buffer_min": rule.setup_buffer_min, "teardown_buffer_min": rule.teardown_buffer_min,
            "approver_scope": {"classroom": "admin_office", "seminar_hall": "admin_office", "lab": "lab_incharge", "amphitheatre": "estate"}[vtype],
        })

    layout = [(1, "A", 12), (2, "B", 12), (3, "C", 10)]
    number = 0
    for building, letter, count in layout:
        for index in range(count):
            floor = index // 4
            capacity = CLASSROOM_CAPACITIES[number]
            features = ["projector"] + (["ac"] if number % 2 == 0 else []) + (["smartboard"] if number % 5 == 0 else []) + (["mic"] if capacity >= 90 else [])
            add(f"{letter}-{floor + 1}{index % 4 + 1:02d}", f"Classroom {letter}-{floor + 1}{index % 4 + 1:02d}", "classroom", building, floor, capacity, features)
            number += 1
    for index, capacity in enumerate([80, 100, 120, 150]):
        add(f"SH-{index + 1}", f"Seminar Hall {index + 1}", "seminar_hall", 4 if index < 2 else 5, 0, capacity, ["projector", "ac", "mic", "smartboard"])
    lab_number = 0
    for lab_type, count, building, depts, supervisor in LAB_PLAN:
        for _ in range(count):
            lab_number += 1
            features = ["projector", "ac"] + (["pcs"] if lab_type in ("cs", "electronics") else [])
            add(f"L-{lab_number}", f"{lab_type.title()} Lab {lab_number}", "lab", 6 if lab_number % 2 else 7, 0, 36 if lab_type in ("cs", "electronics") else 30, features,
                lab_type=lab_type, eligible_depts=depts, needs_supervisor=supervisor or lab_type in ("chem", "mech"))
    add("AMP-1", "Amphitheatre 1", "amphitheatre", 8, 0, 300, ["projector", "ac", "mic", "recording", "stage"])
    add("AMP-2", "Grand Amphitheatre", "amphitheatre", 8, 0, 600, ["projector", "ac", "mic", "recording", "stage"])
    return venues


def build_faculty(rng: random.Random) -> list[dict]:
    faculty: list[dict] = []
    for dept in DEPTS:
        for index in range(8):
            number = len(faculty)
            name = f"Dr. {FIRST_INITIALS[(number * 3) % len(FIRST_INITIALS)]}. {SURNAMES[(number * 7 + index) % len(SURNAMES)]}"
            faculty.append({"id": number + 1, "name": name, "dept": dept})
    return faculty


def build_sections(venues: list[dict]) -> list[dict]:
    classrooms = [v for v in venues if v["type"] == "classroom"]
    sections: list[dict] = []
    for dept in DEPTS:
        for semester in SEMESTERS:
            for name in SECTION_NAMES:
                index = len(sections)
                sections.append({"id": index + 1, "dept": dept, "semester": semester, "name": name, "size": 40 + (index * 7) % 31, "home_venue_id": None})
    load: dict[int, int] = {}
    for section in sorted(sections, key=lambda s: (-s["size"], s["id"])):
        fitting = [v for v in classrooms if v["capacity"] >= section["size"]]
        fitting.sort(key=lambda v: (load.get(v["id"], 0), v["capacity"], v["id"]))
        section["home_venue_id"] = fitting[0]["id"]
        load[fitting[0]["id"]] = load.get(fitting[0]["id"], 0) + 1
    return sections


def build_courses() -> list[dict]:
    courses: list[dict] = []
    for dept in DEPTS:
        for sem_index, semester in enumerate(SEMESTERS):
            topics = COURSE_TOPICS[dept][sem_index * 5:(sem_index + 1) * 5]
            for number, topic in enumerate(topics):
                courses.append({"id": len(courses) + 1, "code": f"{DEPT_PREFIX[dept]}{semester}{number + 1:02d}", "name": topic, "dept": dept, "semester": semester, "kind": "lecture"})
            courses.append({"id": len(courses) + 1, "code": f"HS{semester}0{DEPTS.index(dept) + 1}", "name": "Open Elective", "dept": dept, "semester": semester, "kind": "lecture"})
            for lab_number, lab_type in enumerate(DEPT_LABS[dept]):
                courses.append({"id": len(courses) + 1, "code": f"{DEPT_PREFIX[dept]}{semester}L{lab_number + 1}", "name": f"{lab_type.title()} Laboratory {lab_number + 1}", "dept": dept, "semester": semester, "kind": "lab"})
    return courses


class Planner:
    def __init__(self, venues: list[dict], sections: list[dict], faculty: list[dict], courses: list[dict], rng: random.Random) -> None:
        self.venues = venues
        self.sections = sections
        self.faculty_by_dept: dict[str, list[dict]] = {d: [f for f in faculty if f["dept"] == d] for d in DEPTS}
        self.courses = courses
        self.rng = rng
        self.busy_section: set[tuple[int, int, int]] = set()
        self.busy_faculty: set[tuple[int, int, int]] = set()
        self.busy_venue: set[tuple[int, int, int]] = set()
        self.usage: dict[int, int] = {}
        self.entries: list[dict] = []
        self.lecture_rooms = [v for v in venues if v["type"] in ("classroom", "seminar_hall")]
        self.labs = [v for v in venues if v["type"] == "lab"]

    def free(self, busy: set[tuple[int, int, int]], key: int, weekday: int, first: int, span: int) -> bool:
        return all((key, weekday, p) not in busy for p in range(first, first + span))

    def claim(self, busy: set[tuple[int, int, int]], key: int, weekday: int, first: int, span: int) -> None:
        for p in range(first, first + span):
            busy.add((key, weekday, p))
        if busy is self.busy_venue:
            self.usage[key] = self.usage.get(key, 0) + span

    def pick_room(self, section: dict, weekday: int, first: int, span: int) -> dict | None:
        home = next(v for v in self.venues if v["id"] == section["home_venue_id"])
        if self.free(self.busy_venue, home["id"], weekday, first, span):
            return home
        others = [v for v in self.lecture_rooms if v["capacity"] >= section["size"]]
        others.sort(key=lambda v: (self.usage.get(v["id"], 0), v["capacity"], v["id"]))
        for room in others:
            if self.free(self.busy_venue, room["id"], weekday, first, span):
                return room
        return None

    def pick_lab(self, section: dict, lab_type: str, weekday: int, first: int, span: int) -> dict | None:
        options = [v for v in self.labs if v["lab_type"] == lab_type and section["dept"] in v["eligible_depts"]]
        offset = self.rng.randrange(len(options))
        for step in range(len(options)):
            lab = options[(offset + step) % len(options)]
            if self.free(self.busy_venue, lab["id"], weekday, first, span):
                return lab
        return None

    def place(self, section: dict, course: dict, faculty: dict, span: int, kind: str, lab_type: str | None, used_days: set[int]) -> bool:
        slots = [(d, p) for d in range(6) for p in start_periods(d, span)]
        self.rng.shuffle(slots)
        slots.sort(key=lambda s: s[0] in used_days)
        for weekday, first in slots:
            if not self.free(self.busy_section, section["id"], weekday, first, span):
                continue
            if not self.free(self.busy_faculty, faculty["id"], weekday, first, span):
                continue
            room = self.pick_lab(section, lab_type, weekday, first, span) if lab_type else self.pick_room(section, weekday, first, span)
            if room is None:
                continue
            start_min, end_min = period_bounds(first, span)
            self.claim(self.busy_section, section["id"], weekday, first, span)
            self.claim(self.busy_faculty, faculty["id"], weekday, first, span)
            self.claim(self.busy_venue, room["id"], weekday, first, span)
            self.entries.append({
                "section_id": section["id"], "course_code": course["code"], "course_name": course["name"], "faculty_id": faculty["id"],
                "venue_id": room["id"], "weekday": weekday, "start_min": start_min, "end_min": end_min, "kind": kind,
            })
            used_days.add(weekday)
            return True
        return False

    def plan_section(self, section: dict) -> None:
        dept_courses = [c for c in self.courses if c["dept"] == section["dept"] and c["semester"] == section["semester"]]
        faculty_pool = self.faculty_by_dept[section["dept"]]
        sem_index = SEMESTERS.index(section["semester"])
        labs = [c for c in dept_courses if c["kind"] == "lab"]
        for lab_number, course in enumerate(labs):
            faculty = faculty_pool[(sem_index * 2 + lab_number + 3) % len(faculty_pool)]
            self.place(section, course, faculty, 3, "lab", DEPT_LABS[section["dept"]][lab_number], set())
        theory = [c for c in dept_courses if c["kind"] == "lecture"]
        for number, course in enumerate(theory):
            faculty = faculty_pool[(sem_index * 5 + number) % len(faculty_pool)]
            used_days: set[int] = set()
            for _ in range(2 if course["code"].startswith("HS") else 3):
                self.place(section, course, faculty, 1, "lecture", None, used_days)
            if not course["code"].startswith("HS"):
                self.place(section, course, faculty, 1, "tutorial", None, used_days)


def build_timetable(venues: list[dict], sections: list[dict], faculty: list[dict], courses: list[dict], rng: random.Random) -> list[dict]:
    planner = Planner(venues, sections, faculty, courses, rng)
    ordered = sorted(sections, key=lambda s: (s["semester"], s["dept"], s["name"]))
    for section in ordered:
        planner.plan_section(section)
    entries = planner.entries
    entries.sort(key=lambda e: (e["section_id"], e["weekday"], e["start_min"]))
    for number, entry in enumerate(entries, start=1):
        entry["id"] = number
        entry["version_id"] = 1
        entry["effective_from"] = TERM_START
        entry["effective_to"] = TERM_END
    return entries


def walking_distance(building_a: dict, x: float, y: float) -> int:
    return int(math.hypot(building_a["x"] - x, building_a["y"] - y))


def build_guest_rooms() -> list[dict]:
    plan = [("standard", 8, 2, 2500), ("deluxe", 5, 2, 4000), ("suite", 3, 4, 7000)]
    rooms: list[dict] = []
    for room_type, count, capacity, tariff in plan:
        for _ in range(count):
            number = len(rooms)
            floor = number // 6
            rooms.append({
                "id": number + 1, "code": f"GH-{floor + 1}{number % 6 + 1:02d}", "type": room_type, "beds": 2 if room_type != "suite" else 3,
                "capacity": capacity, "ac": True, "accessible": number in (0, 1, 9), "floor": floor, "tariff_per_night": tariff, "status": "active",
            })
    return rooms


def build_parking(buildings: list[dict]) -> list[dict]:
    plan = [
        ("Visitor Main", "Gate 1", {"cap_car": 60, "cap_bike": 80}, True, (560, 60)),
        ("Admin Lot", "Admin", {"cap_car": 25}, True, (320, 40)),
        ("Amphitheatre Overflow", "South", {"cap_car": 120, "cap_bus": 6}, True, (320, 600)),
        ("VIP Lot", "Admin", {"vip_bays": 10}, False, (360, 80)),
        ("EV Lot", "Gate 1", {"ev_bays": 8}, True, (500, 100)),
    ]
    lots: list[dict] = []
    for number, (name, zone, caps, visitor, (x, y)) in enumerate(plan, start=1):
        lot = {"id": number, "name": name, "zone": zone, "cap_car": 0, "cap_bike": 0, "cap_bus": 0, "ev_bays": 0, "vip_bays": 0, "visitor_allowed": visitor}
        lot.update(caps)
        lot["near_json"] = {str(b["id"]): walking_distance(b, x, y) for b in buildings}
        lots.append(lot)
    return lots


def build_telemetry(entries: list[dict], sections: dict[int, dict], ghost_ids: set[int], rng: random.Random, until: date) -> list[dict]:
    samples: list[dict] = []
    first = until - timedelta(days=28)
    holidays = {d for d, _ in HOLIDAYS}
    seen: set[tuple[int, datetime]] = set()
    for entry in entries:
        size = sections[entry["section_id"]]["size"]
        day = first
        while day < until:
            if day.weekday() == entry["weekday"] and day not in holidays:
                for hour in range(entry["start_min"] // 60, (entry["end_min"] - 1) // 60 + 1):
                    stamp = datetime(day.year, day.month, day.day, hour)
                    if (entry["venue_id"], stamp) in seen:
                        continue
                    seen.add((entry["venue_id"], stamp))
                    ratio = rng.uniform(0.03, 0.14) if entry["id"] in ghost_ids else rng.uniform(0.62, 0.95)
                    samples.append({"venue_id": entry["venue_id"], "ts_hour": stamp, "headcount": max(0, round(size * ratio))})
            day += timedelta(days=1)
    return samples

