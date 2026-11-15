from datetime import date, datetime, timedelta

from app.engine import utilisation
from app.engine.availability import AvailabilityIndex
from app.engine.ghost import detect_ghosts, projected_uplift_hours
from app.engine.parking import lot_timeline, raw_capacity
from app.engine.timeutil import date_range
from app.engine.types import Snapshot
from app.rules import Rules

PEAK_HOURS = range(10, 16)


def guest_house_kpis(snapshot: Snapshot, start: date, end: date) -> dict:
    nights_total = (end - start).days + 1
    rooms = {r.id: r for r in snapshot.guest_rooms}
    occupied = 0
    revenue = 0
    for booking in snapshot.bookings:
        if booking.resource_type != "guest_room" or booking.status != "CONFIRMED":
            continue
        for day in date_range(booking.start_dt.date(), booking.end_dt.date() - timedelta(days=1)):
            if start <= day <= end:
                occupied += 1
                revenue += rooms[booking.resource_id].tariff_per_night
    capacity = len(rooms) * nights_total
    return {"room_nights_occupied": occupied, "occupancy_pct": round(100 * occupied / capacity, 1) if capacity else 0.0, "revenue": revenue, "waitlisted": sum(1 for b in snapshot.bookings if b.status == "WAITLISTED")}


def parking_kpis(snapshot: Snapshot, rules: Rules, scanned_booking_ids: set[int], start: date, end: date) -> dict:
    peak_pct = 0.0
    for lot in snapshot.lots:
        if raw_capacity(lot, "car") <= 0:
            continue
        window_start = datetime(start.year, start.month, start.day)
        window_end = datetime(end.year, end.month, end.day) + timedelta(days=1)
        used = lot_timeline(snapshot, rules, lot, "car", window_start, window_end)["used"]
        if used:
            peak_pct = max(peak_pct, 100 * max(used) / raw_capacity(lot, "car"))
    past = [b for b in snapshot.bookings if b.resource_type == "parking" and b.status in ("CONFIRMED", "NO_SHOW", "COMPLETED") and b.end_dt < snapshot.now]
    no_shows = [b for b in past if b.id not in scanned_booking_ids]
    return {"peak_car_utilisation_pct": round(peak_pct, 1), "past_bookings": len(past), "no_show_rate_pct": round(100 * len(no_shows) / len(past), 1) if past else 0.0}


def approval_kpis(decisions: list[tuple[datetime, datetime]], rules: Rules) -> dict:
    hours = [(decided - created).total_seconds() / 3600 for created, decided in decisions]
    within = sum(1 for h in hours if h <= rules.escalation_after_hours)
    return {
        "decisions": len(hours),
        "avg_decision_hours": round(sum(hours) / len(hours), 1) if hours else 0.0,
        "within_sla_pct": round(100 * within / len(hours), 1) if hours else 0.0,
    }


def compute_kpis(index: AvailabilityIndex, rules: Rules, samples: dict, scanned_booking_ids: set[int], decisions: list[tuple[datetime, datetime]], start: date, end: date) -> dict:
    snapshot = index.snapshot
    rows = utilisation.venue_utilisation(index, start, end)
    classrooms = [r for r in rows if r["type"] == "classroom"]
    hourly = utilisation.hourly_profile(index, start, end)
    peak = [h["utilisation"] for h in hourly if h["hour"] in PEAK_HOURS]
    off_peak = [h["utilisation"] for h in hourly if h["hour"] not in PEAK_HOURS and 9 <= h["hour"] <= 17]
    ghosts = detect_ghosts(snapshot, samples, rules, snapshot.now.date())
    timetable_mean = round(sum(r["timetable"] for r in rows) / len(rows), 3) if rows else 0.0
    total_mean = round(sum(r["total"] for r in rows) / len(rows), 3) if rows else 0.0
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "rooms_counted": len(rows),
        "classroom_time_utilisation_pct": round(100 * sum(r["total"] for r in classrooms) / len(classrooms), 1) if classrooms else 0.0,
        "timetable_utilisation_pct": round(100 * timetable_mean, 1),
        "total_utilisation_pct": round(100 * total_mean, 1),
        "seat_utilisation_pct": round(100 * utilisation.seat_utilisation(snapshot, samples, start, end), 1),
        "peak_utilisation_pct": round(100 * sum(peak) / len(peak), 1) if peak else 0.0,
        "off_peak_utilisation_pct": round(100 * sum(off_peak) / len(off_peak), 1) if off_peak else 0.0,
        "by_type": {k: round(100 * v, 1) for k, v in utilisation.group_mean(rows, "type").items()},
        "by_building": {str(snapshot.buildings[int(k)].name): round(100 * v, 1) for k, v in utilisation.group_mean(rows, "building_id").items()},
        "hourly": hourly,
        "fragmentation": utilisation.fragmentation(index, start, end),
        "ghost_classes": len(ghosts),
        "ghost_bookable_hours_per_week": projected_uplift_hours(ghosts),
        "guest_house": guest_house_kpis(snapshot, start, end),
        "parking": parking_kpis(snapshot, rules, scanned_booking_ids, start, end),
        "approvals": approval_kpis(decisions, rules),
        "bookings": {
            "confirmed": sum(1 for b in snapshot.bookings if b.status == "CONFIRMED"),
            "held": sum(1 for b in snapshot.bookings if b.status == "HELD"),
            "waitlisted": sum(1 for b in snapshot.bookings if b.status == "WAITLISTED"),
        },
    }
