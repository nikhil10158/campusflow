from datetime import datetime

from sqlmodel import Session, select

from app.models.tables import Booking, CalendarEvent, Venue


def add_event(session: Session, booking: Booking) -> CalendarEvent:
    venue = session.get(Venue, booking.resource_id) if booking.resource_type == "venue" else None
    event = CalendarEvent(booking_id=booking.id, venue_code=venue.code if venue else None, owner_id=booking.requester_id, title=booking.event_title, start_dt=booking.start_dt, end_dt=booking.end_dt)
    session.add(event)
    return event


def remove_events(session: Session, booking_id: int) -> None:
    for event in session.exec(select(CalendarEvent).where(CalendarEvent.booking_id == booking_id)):
        session.delete(event)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def to_ics(name: str, events: list[CalendarEvent], redact: bool = False) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CampusFlow//Synthetic Demo//EN", f"X-WR-CALNAME:{name}"]
    for event in events:
        lines += [
            "BEGIN:VEVENT", f"UID:campusflow-{event.id}@synthetic.demo", f"DTSTAMP:{stamp(event.start_dt)}",
            f"DTSTART;TZID=Asia/Kolkata:{stamp(event.start_dt)}", f"DTEND;TZID=Asia/Kolkata:{stamp(event.end_dt)}",
            f"SUMMARY:{'Busy' if redact else event.title.replace(',', ' ')}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
