import random
from datetime import date, datetime, timedelta

from app.config import get_settings
from app.rules import load_rules
from app.seed import campus

DEMO_ROLE_USERS = [
    ("admin", "admin", [], None),
    ("hod.cse", "approver", ["hod:CSE"], "CSE"),
    ("hod.ece", "approver", ["hod:ECE"], "ECE"),
    ("hod.me", "approver", ["hod:ME"], "ME"),
    ("hod.che", "approver", ["hod:CHE"], "CHE"),
    ("hod.eee", "approver", ["hod:EEE"], "EEE"),
    ("labincharge.cse", "approver", ["lab_incharge:cs"], "CSE"),
    ("labincharge.eng", "approver", ["lab_incharge:electronics", "lab_incharge:physics", "lab_incharge:chem", "lab_incharge:mech"], None),
    ("dean", "approver", ["dean"], None),
    ("estate", "approver", ["estate"], None),
    ("guesthouse.mgr", "approver", ["guesthouse_mgr"], None),
    ("parking.officer", "approver", ["parking_officer"], None),
    ("security01", "security", [], None),
]

GUEST_STAYS = [
    (14, date(2026, 11, 19), 2, "vip", "Keynote speaker"), (15, date(2026, 11, 19), 2, "official", "Panel speaker"),
    (9, date(2026, 11, 17), 3, "official", "Accreditation visitor"), (10, date(2026, 11, 18), 2, "faculty_guest", "Visiting professor"),
    (11, date(2026, 11, 20), 4, "faculty_guest", "Guest lecturer"), (12, date(2026, 11, 22), 3, "vendor", "Equipment vendor"),
    (13, date(2026, 11, 25), 5, "official", "Audit team"), (1, date(2026, 11, 23), 2, "parent", "Parent visit"),
    (2, date(2026, 11, 28), 3, "faculty_guest", "Examiner"), (3, date(2026, 12, 1), 4, "other", "Recruiter"),
    (14, date(2026, 11, 24), 4, "vip", "Chief guest"), (16, date(2026, 11, 26), 3, "vip", "Distinguished alumnus"),
]


def at(day: date, hhmm: str) -> datetime:
    hours, minutes = hhmm.split(":")
    return datetime(day.year, day.month, day.day, int(hours), int(minutes))


def room_is_free(entries: list[dict], venue_id: int, day: date, start_min: int, end_min: int) -> bool:
    for entry in entries:
        if entry["venue_id"] == venue_id and entry["weekday"] == day.weekday() and entry["start_min"] < end_min and start_min < entry["end_min"]:
            return False
    return True


def find_free_venue(venues: list[dict], entries: list[dict], vtype: str, day: date, start: str, end: str, lab_type: str | None = None, min_capacity: int = 0) -> dict:
    start_min = campus.hhmm_to_min(start)
    end_min = campus.hhmm_to_min(end)
    for venue in reversed(venues):
        if venue["type"] == vtype and venue["capacity"] >= min_capacity and (lab_type is None or venue["lab_type"] == lab_type):
            if room_is_free(entries, venue["id"], day, start_min - 15, end_min + 15):
                return venue
    raise RuntimeError(f"no free {vtype} for {day}")


def build_users(password_hash: str, faculty: list[dict], sections: list[dict]) -> list[dict]:
    users: list[dict] = []

    def add(email: str, role: str, scopes: list[str], ref_id: int | None, dept: str | None, name: str) -> None:
        users.append({"id": len(users) + 1, "email": f"{email}@jklu.demo", "name": name, "password_hash": password_hash, "role": role, "scopes": scopes, "ref_id": ref_id, "dept": dept})

    for email, role, scopes, dept in DEMO_ROLE_USERS:
        add(email, role, scopes, None, dept, email.replace(".", " ").title())
    per_dept = len(faculty) // len(campus.DEPTS)
    for number in range(10):
        member = faculty[(number % 5) * per_dept + number // 5]
        add(f"faculty{number + 1:02d}", "faculty", [], member["id"], member["dept"], member["name"])
    for number in range(5):
        section = sections[number * 6]
        add(f"student{number + 1:02d}", "student", [], section["id"], section["dept"], f"Student {number + 1:02d}")
    return users


def make_booking(rows: dict[str, list[dict]], **fields) -> dict:
    row = {
        "id": len(rows["booking"]) + 1, "bundle_id": None, "qty": 1, "sponsor_id": None, "purpose": "", "attendees": 0, "rrule": None,
        "priority_class": 4, "status": "CONFIRMED", "hold_expires_at": None, "created_at": None, "meta_json": {},
    }
    row.update(fields)
    rows["booking"].append(row)
    return row


def add_steps(rows: dict[str, list[dict]], booking: dict, scopes: list[str], approved: int, created: datetime) -> None:
    for order, scope in enumerate(scopes, start=1):
        is_done = order <= approved
        rows["approvalstep"].append({
            "id": len(rows["approvalstep"]) + 1, "booking_id": booking["id"], "order": order, "scope": scope,
            "status": "APPROVED" if is_done else "PENDING", "approver_id": 1 if is_done else None, "comment": "Approved (seed)" if is_done else "",
            "decided_at": created if is_done else None, "due_at": created + timedelta(hours=load_rules().escalation_after_hours),
        })


def plates(prefix: int, count: int) -> list[str]:
    return [f"RJ14 CF {prefix * 100 + number:04d}" for number in range(count)]


def build_venue_bookings(rows: dict[str, list[dict]], now: datetime, uid: dict[str, int]) -> dict[str, dict]:
    venues, entries = rows["venue"], rows["timetableentry"]
    by_code = {v["code"]: v for v in venues}
    created = now - timedelta(hours=1)
    hold = created + timedelta(hours=load_rules().hold_ttl_hours)
    made: dict[str, dict] = {}

    def venue_booking(key: str, venue: dict, day: date, start: str, end: str, title: str, attendees: int, requester: str, status: str, scopes: list[str], approved: int, sponsor: str | None = None, bundle_id: int | None = None) -> None:
        booking = make_booking(
            rows, resource_type="venue", resource_id=venue["id"], requester_id=uid[requester], sponsor_id=uid[sponsor] if sponsor else None,
            event_title=title, attendees=attendees, start_dt=at(day, start), end_dt=at(day, end), status=status, bundle_id=bundle_id,
            hold_expires_at=hold if status == "HELD" else None, created_at=created, meta_json={"seed": True},
        )
        add_steps(rows, booking, scopes, approved, created)
        made[key] = booking

    venue_booking("concert", by_code["AMP-2"], date(2026, 11, 20), "17:00", "20:00", "Founders Day Concert", 450, "faculty03", "CONFIRMED", ["estate", "dean"], 2, bundle_id=1)
    venue_booking("keynote", by_code["AMP-1"], date(2026, 11, 18), "10:00", "12:00", "AI Workshop Keynote", 180, "faculty01", "CONFIRMED", ["estate", "dean"], 2)
    hall = find_free_venue(venues, entries, "seminar_hall", date(2026, 11, 19), "14:00", "16:00", min_capacity=60)
    venue_booking("fdp", hall, date(2026, 11, 19), "14:00", "16:00", "Faculty Development Workshop", 60, "faculty04", "CONFIRMED", ["admin_office"], 1)
    classroom = find_free_venue(venues, entries, "classroom", date(2026, 11, 18), "15:00", "16:00", min_capacity=55)
    venue_booking("extra", classroom, date(2026, 11, 18), "15:00", "16:00", "Extra Lecture: Algorithms", 55, "faculty01", "CONFIRMED", ["admin_office"], 1)
    classroom = find_free_venue(venues, entries, "classroom", date(2026, 11, 19), "16:00", "17:00", min_capacity=40)
    venue_booking("quiz", classroom, date(2026, 11, 19), "16:00", "17:00", "CSE Quiz Revision", 40, "student01", "CONFIRMED", ["admin_office"], 1, sponsor="faculty01")
    classroom = find_free_venue(venues, entries, "classroom", date(2026, 11, 17), "11:00", "12:00", min_capacity=45)
    venue_booking("club", classroom, date(2026, 11, 17), "11:00", "12:00", "Robotics Club Meeting", 45, "student02", "CONFIRMED", ["admin_office"], 1, sponsor="faculty02")
    venue_booking("alumni", by_code["AMP-1"], date(2026, 12, 2), "15:00", "18:00", "Alumni Meet", 120, "faculty02", "HELD", ["estate", "dean"], 1)
    venue_booking("orientation", by_code["AMP-2"], date(2026, 11, 25), "09:00", "11:00", "Orientation Rehearsal", 300, "faculty05", "HELD", ["estate", "dean"], 0)
    lab = find_free_venue(venues, entries, "lab", date(2026, 11, 26), "14:00", "17:00", "cs", min_capacity=30)
    venue_booking("hackathon", lab, date(2026, 11, 26), "14:00", "17:00", "CS Hackathon Prep", 30, "faculty01", "HELD", ["lab_incharge:cs", "hod:CSE"], 0)
    classroom = find_free_venue(venues, entries, "classroom", date(2026, 11, 23), "10:00", "11:00", min_capacity=50)
    venue_booking("mock", classroom, date(2026, 11, 23), "10:00", "11:00", "Mock Interview Session", 50, "student03", "HELD", ["admin_office"], 0, sponsor="faculty02")
    return made


def build_guest_bookings(rows: dict[str, list[dict]], now: datetime, uid: dict[str, int]) -> None:
    created = now - timedelta(hours=1)
    priority = load_rules().priority_classes
    for number, (room_id, start_day, nights, category, role) in enumerate(GUEST_STAYS, start=1):
        rows["guest"].append({"id": number, "name": f"Guest {number:02d} ({role})", "org": "Synthetic Org", "category": category})
        booking = make_booking(
            rows, resource_type="guest_room", resource_id=room_id, requester_id=uid["faculty03"] if number <= 2 else uid["faculty01"], event_title=f"Guest stay: {role}",
            qty=1, attendees=1, start_dt=at(start_day, "14:00"), end_dt=at(start_day + timedelta(days=nights), "11:00"), priority_class=priority.get(category, priority["other"]),
            bundle_id=1 if number <= 2 else None, created_at=created, meta_json={"seed": True, "guest_ids": [number], "guests": 1, "host": "Host faculty"},
        )
        add_steps(rows, booking, ["guesthouse_mgr"], 1, created)
    rows["guest"].append({"id": 13, "name": "Guest 13 (External speaker)", "org": "Synthetic Org", "category": "official"})
    held = make_booking(
        rows, resource_type="guest_room", resource_id=5, requester_id=uid["faculty02"], event_title="Guest stay: Alumni Meet speaker", attendees=1,
        start_dt=at(date(2026, 12, 2), "14:00"), end_dt=at(date(2026, 12, 4), "11:00"), priority_class=2, status="HELD",
        hold_expires_at=created + timedelta(hours=load_rules().hold_ttl_hours), created_at=created, meta_json={"seed": True, "guest_ids": [13], "guests": 1, "host": "Alumni Meet"},
    )
    add_steps(rows, held, ["guesthouse_mgr"], 0, created)
    rows["guest"].append({"id": 14, "name": "Guest 14 (Waitlisted VIP)", "org": "Synthetic Org", "category": "vip"})
    make_booking(
        rows, resource_type="guest_room", resource_id=16, requester_id=uid["faculty03"], event_title="Guest stay: Waitlisted VIP", attendees=1,
        start_dt=at(date(2026, 11, 27), "14:00"), end_dt=at(date(2026, 11, 29), "11:00"), priority_class=1, status="WAITLISTED", created_at=created,
        meta_json={"seed": True, "guest_ids": [14], "guests": 1, "host": "Chancellor's office", "requested_type": "suite"},
    )


def build_parking_bookings(rows: dict[str, list[dict]], now: datetime, uid: dict[str, int]) -> None:
    created = now - timedelta(hours=1)
    hold = created + timedelta(hours=load_rules().hold_ttl_hours)
    plan = [
        (3, "Founders Day Concert parking", date(2026, 11, 20), "15:00", "21:00", {"car": 30}, 450, "CONFIRMED", 1, "faculty03"),
        (1, "AI Workshop visitor parking", date(2026, 11, 18), "09:00", "13:00", {"car": 20}, 180, "CONFIRMED", None, "faculty01"),
        (5, "Faculty workshop EV parking", date(2026, 11, 19), "13:30", "16:30", {"ev": 3}, 60, "CONFIRMED", None, "faculty04"),
        (1, "Alumni Meet parking", date(2026, 12, 2), "14:00", "18:00", {"car": 25}, 120, "HELD", None, "faculty02"),
        (3, "Orientation bus parking", date(2026, 11, 25), "08:00", "12:00", {"bus": 2}, 300, "HELD", None, "faculty05"),
    ]
    for number, (lot_id, title, day, start, end, vehicles, attendees, status, bundle_id, who) in enumerate(plan, start=1):
        total = sum(vehicles.values())
        booking = make_booking(
            rows, resource_type="parking", resource_id=lot_id, requester_id=uid[who], event_title=title, qty=total, attendees=attendees,
            start_dt=at(day, start), end_dt=at(day, end), status=status, bundle_id=bundle_id, hold_expires_at=hold if status == "HELD" else None,
            created_at=created, meta_json={"seed": True, "vehicles": vehicles, "plates": plates(number, total)},
        )
        add_steps(rows, booking, ["parking_officer"], 1 if status == "CONFIRMED" else 0, created)


def build_exceptions(entries: list[dict], faculty: list[dict]) -> list[dict]:
    exceptions: list[dict] = []

    def add(entry: dict, day: date, reason: str) -> None:
        exceptions.append({"id": len(exceptions) + 1, "entry_id": entry["id"], "date": day, "type": "cancelled", "reason": reason, "status": "APPROVED", "created_by": 1, "venue_id": None, "start_min": None, "end_min": None})

    def next_day(weekday: int, after: date) -> date:
        return after + timedelta(days=(weekday - after.weekday()) % 7)

    chosen_weekdays: set[int] = set()
    for entry in entries:
        if entry["kind"] == "lecture" and entry["weekday"] not in chosen_weekdays and entry["weekday"] < 5 and entry["start_min"] >= 600 and entry["id"] % 3 == 0:
            chosen_weekdays.add(entry["weekday"])
            add(entry, next_day(entry["weekday"], date(2026, 11, 17)), "Faculty on official duty")
        if len(chosen_weekdays) == 3:
            break
    on_leave = faculty[1]["id"]
    for entry in entries:
        if entry["faculty_id"] == on_leave and entry["weekday"] == 2:
            add(entry, date(2026, 11, 25), "Faculty leave")
    return exceptions


def pick_ghosts(entries: list[dict], count: int) -> set[int]:
    candidates = [e for e in entries if e["kind"] == "lecture" and e["weekday"] < 5 and e["start_min"] >= 600]
    step = max(1, len(candidates) // (count + 1))
    return {candidates[(index + 1) * step]["id"] for index in range(count)}


def build_world(password_hash: str) -> dict[str, list[dict]]:
    rng = random.Random(campus.SEED)
    now = get_settings().demo_now
    buildings = campus.build_buildings()
    venues = campus.build_venues()
    faculty = campus.build_faculty(rng)
    sections = campus.build_sections(venues)
    courses = campus.build_courses()
    entries = campus.build_timetable(venues, sections, faculty, courses, rng)
    users = build_users(password_hash, faculty, sections)
    uid = {u["email"].split("@")[0]: u["id"] for u in users}
    rows: dict[str, list[dict]] = {
        "building": buildings, "venue": venues, "term": [{"id": 1, "name": "Autumn 2026 (synthetic)", "start": campus.TERM_START, "end": campus.TERM_END}],
        "holiday": [{"id": n, "date": d, "name": name} for n, (d, name) in enumerate(campus.HOLIDAYS, start=1)],
        "section": sections, "faculty": faculty, "course": courses, "user": users,
        "timetableversion": [{"id": 1, "term_id": 1, "source_file": "synthetic-generator", "format": "generated", "status": "ACTIVE", "issues_json": [], "uploaded_by": 1, "created_at": now - timedelta(days=100)}],
        "timetableentry": entries, "scheduleexception": build_exceptions(entries, faculty),
        "bookingbundle": [{"id": 1, "title": "Founders Day Concert", "requester_id": uid["faculty03"], "status": "CONFIRMED", "created_at": now - timedelta(hours=1)}],
        "booking": [], "approvalstep": [], "guest": [], "guestroom": campus.build_guest_rooms(), "parkinglot": campus.build_parking(buildings),
        "maintenance": [
            {"id": 1, "resource_type": "venue", "resource_id": next(v["id"] for v in venues if v["code"] == "L-6"), "start_dt": at(date(2026, 11, 24), "00:00"), "end_dt": at(date(2026, 11, 26), "00:00"), "reason": "Oscilloscope calibration"},
            {"id": 2, "resource_type": "venue", "resource_id": next(v["id"] for v in venues if v["code"] == "AMP-1"), "start_dt": at(date(2026, 11, 30), "08:00"), "end_dt": at(date(2026, 11, 30), "18:00"), "reason": "Stage lighting repair"},
            {"id": 3, "resource_type": "guest_room", "resource_id": 6, "start_dt": at(date(2026, 11, 22), "00:00"), "end_dt": at(date(2026, 11, 24), "00:00"), "reason": "Plumbing repair"},
        ],
    }
    build_venue_bookings(rows, now, uid)
    build_guest_bookings(rows, now, uid)
    build_parking_bookings(rows, now, uid)
    ghosts = pick_ghosts(entries, 6)
    rows["occupancysample"] = campus.build_telemetry(entries, {s["id"]: s for s in sections}, ghosts, rng, now.date())
    return rows

