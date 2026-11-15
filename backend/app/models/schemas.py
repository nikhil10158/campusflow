from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    scopes: list[str]
    dept: str | None
    ref_id: int | None


class LoginOut(BaseModel):
    token: str
    user: UserOut


class BookingIn(BaseModel):
    resource_type: Literal["venue", "guest_room", "parking"]
    resource_id: int
    start: datetime
    end: datetime
    event_title: str = "Untitled request"
    purpose: str = ""
    attendees: int = 0
    qty: int = 1
    sponsor_id: int | None = None
    host_ref: str | None = None
    features: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class BundleIn(BaseModel):
    title: str
    components: list[BookingIn]
    external_speakers: int = 0
    recording: bool = False


class DecisionIn(BaseModel):
    comment: str = ""


class RejectIn(BaseModel):
    comment: str


class SearchIn(BaseModel):
    start: datetime
    end: datetime
    attendees: int = 0
    types: list[str] = Field(default_factory=lambda: ["classroom", "seminar_hall"])
    required_features: list[str] = Field(default_factory=list)
    optional_features: list[str] = Field(default_factory=list)
    near_venue_id: int | None = None
    building_id: int | None = None
    dept: str | None = None
    accessible: bool = False
    repeat_weeks: int = 1


class CohortIn(BaseModel):
    section_ids: list[int] = Field(default_factory=list)
    semester: int | None = None
    dept: str | None = None
    faculty_ids: list[int] = Field(default_factory=list)
    start_date: date
    end_date: date
    duration_min: int = 60
    earliest: str = "09:00"
    latest: str = "18:00"


class GroupGuestIn(BaseModel):
    name: str
    category: str = "other"
    needs_accessible: bool = False


class GroupAllocateIn(BaseModel):
    start: datetime
    end: datetime
    guests: list[GroupGuestIn]
    must_share: list[tuple[int, int]] = Field(default_factory=list)
    must_not_share: list[tuple[int, int]] = Field(default_factory=list)


class ReleaseIn(BaseModel):
    entry_id: int
    date: date
    reason: str = "Class will not be held"


class DisruptionIn(BaseModel):
    kind: Literal["venue", "faculty", "lot"] = "venue"
    description: str = ""
    start: datetime
    end: datetime
    venue_ids: list[int] = Field(default_factory=list)
    building_id: int | None = None
    faculty_id: int | None = None
    lot_id: int | None = None


class ScanIn(BaseModel):
    token: str
    lot_id: int | None = None


class DemoNowIn(BaseModel):
    now: datetime


class AgentChatIn(BaseModel):
    message: str
    clarification: dict[str, Any] | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class PolicyAskIn(BaseModel):
    question: str


class ReplaceComponentIn(BaseModel):
    booking_id: int
    replacement: BookingIn


class BatchIn(BaseModel):
    events: int = 20
    seed: int = 7
    first_day: date = date(2026, 12, 1)
