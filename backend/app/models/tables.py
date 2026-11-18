from datetime import date as DateType
from pydantic import NaiveDatetime

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


class Building(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    x: float
    y: float
    zone: str


class Venue(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    name: str
    type: str
    building_id: int = Field(foreign_key="building.id", index=True)
    floor: int = 0
    capacity: int
    features: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    lab_type: str | None = None
    eligible_depts: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    needs_supervisor: bool = False
    accessible: bool = True
    bookable: bool = True
    setup_buffer_min: int = 0
    teardown_buffer_min: int = 0
    approver_scope: str = "admin_office"


class Term(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    start: DateType
    end: DateType


class Holiday(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    date: DateType = Field(index=True)
    name: str


class Section(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    dept: str = Field(index=True)
    semester: int
    name: str
    size: int
    home_venue_id: int | None = Field(default=None, foreign_key="venue.id")


class Faculty(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    dept: str = Field(index=True)


class Course(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(index=True)
    name: str
    dept: str
    semester: int
    kind: str = "lecture"


class TimetableVersion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    term_id: int = Field(foreign_key="term.id", index=True)
    source_file: str
    format: str
    status: str = "DRAFT"
    issues_json: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    uploaded_by: int | None = Field(default=None, foreign_key="user.id")
    created_at: NaiveDatetime


class TimetableEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    version_id: int = Field(foreign_key="timetableversion.id", index=True)
    section_id: int = Field(foreign_key="section.id", index=True)
    course_code: str
    course_name: str
    faculty_id: int | None = Field(default=None, foreign_key="faculty.id", index=True)
    venue_id: int = Field(foreign_key="venue.id", index=True)
    weekday: int
    start_min: int
    end_min: int
    kind: str = "lecture"
    effective_from: DateType
    effective_to: DateType


class ScheduleException(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    entry_id: int = Field(foreign_key="timetableentry.id", index=True)
    date: DateType
    type: str
    reason: str = ""
    status: str = "PROPOSED"
    created_by: int | None = Field(default=None, foreign_key="user.id")
    venue_id: int | None = Field(default=None, foreign_key="venue.id")
    start_min: int | None = None
    end_min: int | None = None


class BookingBundle(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    requester_id: int = Field(foreign_key="user.id", index=True)
    status: str = "DRAFT"
    created_at: NaiveDatetime


class Booking(SQLModel, table=True):
    __table_args__ = (Index("ix_booking_resource_window", "resource_type", "resource_id", "start_dt", "end_dt"),)
    id: int | None = Field(default=None, primary_key=True)
    bundle_id: int | None = Field(default=None, foreign_key="bookingbundle.id", index=True)
    resource_type: str
    resource_id: int
    qty: int = 1
    requester_id: int = Field(foreign_key="user.id", index=True)
    sponsor_id: int | None = Field(default=None, foreign_key="user.id", index=True)
    event_title: str
    purpose: str = ""
    attendees: int = 0
    start_dt: NaiveDatetime
    end_dt: NaiveDatetime
    rrule: str | None = None
    priority_class: int = 4
    status: str = "HELD"
    hold_expires_at: NaiveDatetime | None = None
    created_at: NaiveDatetime | None = None
    meta_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class ApprovalStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    booking_id: int = Field(foreign_key="booking.id", index=True)
    order: int
    scope: str
    status: str = "PENDING"
    approver_id: int | None = Field(default=None, foreign_key="user.id")
    comment: str = ""
    decided_at: NaiveDatetime | None = None
    due_at: NaiveDatetime | None = None


class Maintenance(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    resource_type: str
    resource_id: int
    start_dt: NaiveDatetime
    end_dt: NaiveDatetime
    reason: str = ""


class GuestRoom(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    type: str
    beds: int
    capacity: int
    ac: bool = True
    accessible: bool = False
    floor: int = 0
    tariff_per_night: int
    status: str = "active"


class Guest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    org: str
    category: str


class ParkingLot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    zone: str
    cap_car: int = 0
    cap_bike: int = 0
    cap_bus: int = 0
    ev_bays: int = 0
    vip_bays: int = 0
    visitor_allowed: bool = True
    near_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Pass(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    booking_id: int = Field(foreign_key="booking.id", index=True)
    type: str
    resource_id: int
    token_hmac: str = Field(index=True)
    plate: str | None = None
    valid_from: NaiveDatetime
    valid_to: NaiveDatetime
    scanned_at: NaiveDatetime | None = None
    revoked: bool = False


class OccupancySample(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    venue_id: int = Field(foreign_key="venue.id", index=True)
    ts_hour: NaiveDatetime
    headcount: int


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str = ""
    password_hash: str
    role: str
    scopes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    ref_id: int | None = None
    dept: str | None = None


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ts: NaiveDatetime
    actor: str
    action: str
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON))
    prev_hash: str
    hash: str


class Notification(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    channel: str
    recipient: str
    subject: str
    body: str
    created_at: NaiveDatetime
    related_booking_id: int | None = None


class UserNotification(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    kind: str = "booking"
    title: str
    body: str = ""
    booking_id: int | None = Field(default=None, index=True)
    read_at: NaiveDatetime | None = None
    created_at: NaiveDatetime


class CalendarEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    booking_id: int | None = Field(default=None, index=True)
    venue_code: str | None = None
    owner_id: int | None = None
    title: str
    start_dt: NaiveDatetime
    end_dt: NaiveDatetime


class LLMUsage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    day: DateType = Field(index=True)
    model: str
    calls: int = 0


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str
    status: str = "PENDING"
    created_by: int | None = None
    created_at: NaiveDatetime
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str


class Disruption(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str
    description: str
    start_dt: NaiveDatetime
    end_dt: NaiveDatetime
    venue_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    plan_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "PROPOSED"
    created_by: int | None = None


ALL_TABLES = [
    Building, Venue, Term, Holiday, Section, Faculty, Course, User, TimetableVersion, TimetableEntry,
    ScheduleException, BookingBundle, Booking, ApprovalStep, Maintenance, GuestRoom, Guest, ParkingLot,
    Pass, OccupancySample, AuditLog, Notification, UserNotification, CalendarEvent, LLMUsage, Job, Setting, Disruption,
]


