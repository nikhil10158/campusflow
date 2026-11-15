from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class BuildingInfo:
    id: int
    name: str
    x: float
    y: float
    zone: str


@dataclass(frozen=True, slots=True)
class VenueInfo:
    id: int
    code: str
    name: str
    type: str
    building_id: int
    floor: int
    capacity: int
    features: tuple[str, ...]
    lab_type: str | None
    eligible_depts: tuple[str, ...]
    needs_supervisor: bool
    accessible: bool
    bookable: bool
    setup_buffer_min: int
    teardown_buffer_min: int
    approver_scope: str


@dataclass(frozen=True, slots=True)
class SectionInfo:
    id: int
    dept: str
    semester: int
    name: str
    size: int
    home_venue_id: int | None


@dataclass(frozen=True, slots=True)
class EntryInfo:
    id: int
    section_id: int
    course_code: str
    course_name: str
    faculty_id: int | None
    venue_id: int
    weekday: int
    start_min: int
    end_min: int
    kind: str
    effective_from: date
    effective_to: date


@dataclass(frozen=True, slots=True)
class ExceptionInfo:
    id: int
    entry_id: int
    date: date
    type: str
    status: str
    venue_id: int | None
    start_min: int | None
    end_min: int | None


@dataclass(frozen=True, slots=True)
class BookingInfo:
    id: int
    bundle_id: int | None
    resource_type: str
    resource_id: int
    qty: int
    requester_id: int
    event_title: str
    attendees: int
    start_dt: datetime
    end_dt: datetime
    priority_class: int
    status: str
    hold_expires_at: datetime | None
    meta: dict


@dataclass(frozen=True, slots=True)
class MaintenanceInfo:
    id: int
    resource_type: str
    resource_id: int
    start_dt: datetime
    end_dt: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class GuestRoomInfo:
    id: int
    code: str
    type: str
    beds: int
    capacity: int
    accessible: bool
    tariff_per_night: int
    status: str


@dataclass(frozen=True, slots=True)
class LotInfo:
    id: int
    name: str
    zone: str
    cap_car: int
    cap_bike: int
    cap_bus: int
    ev_bays: int
    vip_bays: int
    visitor_allowed: bool
    near: dict


@dataclass(frozen=True, slots=True)
class StepInfo:
    id: int
    booking_id: int
    order: int
    scope: str
    status: str


@dataclass(frozen=True, slots=True)
class PassInfo:
    id: int
    booking_id: int
    type: str
    resource_id: int
    plate: str | None
    valid_from: datetime
    valid_to: datetime
    revoked: bool


@dataclass
class Snapshot:
    now: datetime
    venues: list[VenueInfo] = field(default_factory=list)
    buildings: dict[int, BuildingInfo] = field(default_factory=dict)
    sections: dict[int, SectionInfo] = field(default_factory=dict)
    faculty: dict[int, str] = field(default_factory=dict)
    entries: list[EntryInfo] = field(default_factory=list)
    exceptions: list[ExceptionInfo] = field(default_factory=list)
    holidays: set[date] = field(default_factory=set)
    bookings: list[BookingInfo] = field(default_factory=list)
    maintenance: list[MaintenanceInfo] = field(default_factory=list)
    guest_rooms: list[GuestRoomInfo] = field(default_factory=list)
    lots: list[LotInfo] = field(default_factory=list)
    steps: list[StepInfo] = field(default_factory=list)
    passes: list[PassInfo] = field(default_factory=list)
    ghost_entry_ids: set[int] = field(default_factory=set)
    version: int = 0

    def venue(self, venue_id: int) -> VenueInfo:
        return self.venues_by_id()[venue_id]

    def venues_by_id(self) -> dict[int, VenueInfo]:
        cached = self.__dict__.get("_venues_by_id")
        if cached is None:
            cached = {v.id: v for v in self.venues}
            self.__dict__["_venues_by_id"] = cached
        return cached

    def entry(self, entry_id: int) -> EntryInfo | None:
        cached = self.__dict__.get("_entries_by_id")
        if cached is None:
            cached = {e.id: e for e in self.entries}
            self.__dict__["_entries_by_id"] = cached
        return cached.get(entry_id)


@dataclass
class BookingRequest:
    resource_type: str
    resource_id: int
    start: datetime
    end: datetime
    attendees: int = 0
    qty: int = 1
    title: str = ""
    purpose: str = ""
    requester_role: str = "faculty"
    requester_id: int | None = None
    requester_dept: str | None = None
    sponsor_id: int | None = None
    host_ref: str | None = None
    features: tuple[str, ...] = ()
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Violation:
    code: str
    rule_id: str
    severity: str
    message: str
    fixable_by: str = "requester"

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "fixable_by": self.fixable_by,
        }


@dataclass(frozen=True, slots=True)
class Segment:
    start_slot: int
    end_slot: int
    layer: str
    label: str
    source_id: int | None = None
    ghost: bool = False

    def time_text(self) -> str:
        start = self.start_slot * 15
        end = self.end_slot * 15
        return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"

    def as_dict(self) -> dict:
        return {
            "start_slot": self.start_slot,
            "end_slot": self.end_slot,
            "time": self.time_text(),
            "layer": self.layer,
            "label": self.label,
            "source_id": self.source_id,
            "ghost": self.ghost,
        }
