from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import tables as t
from app.services.clock import get_now
from app.services.snapshot import get_index

ROOM_TYPES = ("classroom", "seminar_hall", "lab", "amphitheatre")
COUNTED = ("CONFIRMED", "COMPLETED")
BOOKABLE_HOURS_PER_DAY = 15


def hours_of(booking: t.Booking) -> float:
    return (booking.end_dt - booking.start_dt).total_seconds() / 3600


def utilization_summary(session: Session) -> dict:
    now = get_now(session)
    bookings = session.exec(select(t.Booking)).all()
    venues = session.exec(select(t.Venue)).all()
    venue_by_id = {venue.id: venue for venue in venues}
    status_counts = Counter(booking.status for booking in bookings)
    usage: dict[int, dict] = {}
    for booking in bookings:
        if booking.resource_type != "venue" or booking.status not in COUNTED or booking.resource_id not in venue_by_id:
            continue
        venue = venue_by_id[booking.resource_id]
        row = usage.setdefault(venue.id, {"venue_id": venue.id, "code": venue.code, "name": venue.name, "type": venue.type, "capacity": venue.capacity, "bookings": 0, "hours": 0.0})
        row["bookings"] += 1
        row["hours"] = round(row["hours"] + hours_of(booking), 1)
    most_used = sorted(usage.values(), key=lambda row: (-row["bookings"], -row["hours"], row["code"]))[:8]

    under_maintenance = {(m.resource_type, m.resource_id) for m in session.exec(select(t.Maintenance)).all() if m.start_dt <= now < m.end_dt}
    guest_rooms = session.exec(select(t.GuestRoom)).all()
    lots = session.exec(select(t.ParkingLot)).all()
    rooms = [venue for venue in venues if venue.type in ROOM_TYPES and venue.bookable]
    available_rooms = [venue for venue in rooms if ("venue", venue.id) not in under_maintenance]
    index = get_index(session)
    quarter = timedelta(minutes=15)
    vacant = [venue for venue in available_rooms if index.covers(now, now + quarter) and index.is_free(venue.id, now, now + quarter, with_buffers=False)]
    by_type = Counter(venue.type for venue in available_rooms)
    vacant_by_type = Counter(venue.type for venue in vacant)

    month_hours: dict[str, float] = defaultdict(float)
    month_count: Counter = Counter()
    for booking in bookings:
        if booking.resource_type == "venue" and booking.status in COUNTED:
            key = f"{booking.start_dt:%Y-%m}"
            month_hours[key] += hours_of(booking)
            month_count[key] += 1
    capacity_per_day = max(len(rooms), 1) * BOOKABLE_HOURS_PER_DAY
    monthly = []
    for key in sorted(month_hours):
        year, month = int(key[:4]), int(key[5:])
        following = date(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
        span = (following - date(year, month, 1)).days
        monthly.append({"month": key, "bookings": month_count[key], "hours": round(month_hours[key], 1), "utilisation_pct": round(100 * month_hours[key] / (capacity_per_day * span), 2)})

    return {
        "as_of": now.isoformat(),
        "total_bookings": len(bookings),
        "by_status": dict(status_counts),
        "most_used": most_used,
        "resources": {
            "rooms_total": len(rooms), "rooms_available": len(available_rooms), "guest_rooms_total": len(guest_rooms),
            "guest_rooms_available": sum(1 for room in guest_rooms if ("guest_room", room.id) not in under_maintenance),
            "parking_lots": len(lots), "available_by_type": dict(by_type),
        },
        "vacant_now": {"count": len(vacant), "by_type": dict(vacant_by_type), "rooms": [{"code": venue.code, "type": venue.type, "capacity": venue.capacity} for venue in sorted(vacant, key=lambda v: v.code)[:12]]},
        "monthly": monthly,
    }
