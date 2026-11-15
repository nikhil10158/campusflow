import base64
from collections import defaultdict
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.config import get_settings
from app.engine.timeutil import at_minute
from app.ingest import normalise, validate
from app.ingest.csv import parse_csv
from app.ingest.gemini_fallback import extract_with_gemini
from app.ingest.grid_xlsx import parse_grid_xlsx
from app.ingest.pdf import parse_pdf
from app.ingest.types import NormalisedEntry, ParsedFile
from app.models import tables as t
from app.services import audit
from app.services.clock import get_now
from app.services.errors import BadRequest, Conflict, NotFound

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def detect_format(filename: str, content: bytes) -> str:
    name = filename.lower()
    if name.endswith(".csv") or name.endswith(".txt"):
        return "csv"
    if name.endswith(".xlsx") or content[:2] == b"PK":
        return "grid_xlsx"
    if name.endswith(".pdf") or content[:4] == b"%PDF":
        return "grid_pdf"
    raise BadRequest("Upload a CSV, an Excel grid (.xlsx) or a PDF grid")


def parse_upload(fmt: str, content: bytes, answers: dict[str, str]) -> ParsedFile:
    if fmt == "csv":
        return parse_csv(content, answers)
    if fmt == "grid_xlsx":
        return parse_grid_xlsx(content)
    parsed = parse_pdf(content)
    if not parsed.rows:
        rows = extract_with_gemini(content)
        if rows:
            parsed.rows = rows
            parsed.ai_extracted = True
            parsed.notes.append("AI-extracted - please review every row before importing")
    return parsed


def active_version(session: Session) -> t.TimetableVersion | None:
    return session.exec(select(t.TimetableVersion).where(t.TimetableVersion.status == "ACTIVE")).first()


def entry_key(entry: NormalisedEntry) -> tuple:
    return (entry.section_id, entry.weekday, entry.start_min, entry.course_code)


def diff_against_active(session: Session, entries: list[NormalisedEntry]) -> dict:
    version = active_version(session)
    sections = {e.section_id for e in entries if e.section_id is not None}
    old_rows = [e for e in session.exec(select(t.TimetableEntry).where(t.TimetableEntry.version_id == version.id)) if e.section_id in sections] if version else []
    complete = [e for e in entries if validate.is_complete(e)]
    new_keys = {entry_key(e): e for e in complete}
    old_keys = {(o.section_id, o.weekday, o.start_min, o.course_code): o for o in old_rows}
    added = [e for k, e in new_keys.items() if k not in old_keys]
    removed = [o for k, o in old_keys.items() if k not in new_keys]
    moved = []
    for new in list(added):
        match = next((o for o in removed if o.section_id == new.section_id and o.course_code == new.course_code and o.weekday == new.weekday), None) or next((o for o in removed if o.section_id == new.section_id and o.course_code == new.course_code and o.start_min == new.start_min), None)
        if match:
            moved.append((match, new))
            added.remove(new)
            removed.remove(match)
    venues = {v.id: v.code for v in session.exec(select(t.Venue))}
    changed_venue = [(o, n) for k, n in new_keys.items() if (o := old_keys.get(k)) and o.venue_id != n.venue_id]
    return {
        "sections": sorted(sections),
        "added": [{"section_id": e.section_id, "course": e.course_code, "weekday": e.weekday, "start_min": e.start_min, "end_min": e.end_min, "venue": venues.get(e.venue_id)} for e in added],
        "removed": [{"section_id": o.section_id, "course": o.course_code, "weekday": o.weekday, "start_min": o.start_min, "end_min": o.end_min, "venue": venues.get(o.venue_id)} for o in removed],
        "moved": [{"section_id": n.section_id, "course": n.course_code, "from": {"weekday": o.weekday, "start_min": o.start_min, "venue": venues.get(o.venue_id)}, "to": {"weekday": n.weekday, "start_min": n.start_min, "venue": venues.get(n.venue_id)}} for o, n in moved]
        + [{"section_id": n.section_id, "course": n.course_code, "from": {"weekday": o.weekday, "start_min": o.start_min, "venue": venues.get(o.venue_id)}, "to": {"weekday": n.weekday, "start_min": n.start_min, "venue": venues.get(n.venue_id)}} for o, n in changed_venue],
        "unchanged": len(new_keys) - len(added) - len(moved) - len(changed_venue),
    }


def affected_bookings(session: Session, entries: list[NormalisedEntry], diff: dict) -> list[dict]:
    changed = {(item["section_id"], item["course"]) for item in diff["added"]} | {(item["section_id"], item["course"]) for item in diff["moved"]}
    now = get_now(session)
    term = session.exec(select(t.Term)).first()
    found = []
    for booking in session.exec(select(t.Booking).where(t.Booking.resource_type == "venue", t.Booking.status.in_(["CONFIRMED", "HELD"]))):
        if booking.end_dt < now:
            continue
        for entry in entries:
            if (entry.section_id, entry.course_code) not in changed or not validate.is_complete(entry) or entry.venue_id != booking.resource_id:
                continue
            same_day = entry.weekday == booking.start_dt.weekday() and term and term.start <= booking.start_dt.date() <= term.end
            if same_day and entry.start_min < booking.end_dt.hour * 60 + booking.end_dt.minute and booking.start_dt.hour * 60 + booking.start_dt.minute < entry.end_min:
                found.append({"booking_id": booking.id, "title": booking.event_title, "start": booking.start_dt.isoformat(), "conflicts_with": f"{entry.course_code} ({entry.source})"})
                break
    return found


def run_pipeline(session: Session, job: t.Job) -> dict:
    payload = job.payload
    content = base64.b64decode(payload["content_b64"])
    answers = payload.get("answers", {})
    parsed = parse_upload(payload["format"], content, answers)
    reference = normalise.build_reference(session)
    result = normalise.normalise_rows(parsed.rows, reference, answers)
    clarifications = [c.as_dict() for c in parsed.clarifications] + [c.as_dict() for c in result.clarifications]
    sections = {e.section_id for e in result.entries if e.section_id is not None}
    version = active_version(session)
    existing = [
        validate.ExistingEntry(e.section_id, e.weekday, e.start_min, e.end_min, e.faculty_id, e.venue_id, e.course_code)
        for e in session.exec(select(t.TimetableEntry).where(t.TimetableEntry.version_id == version.id)) if e.section_id not in sections
    ] if version else []
    issues = [i.as_dict() for i in validate.validate(result, reference, existing)]
    diff = diff_against_active(session, result.entries)
    summary = {
        "format": parsed.format, "rows": len(parsed.rows), "ai_extracted": parsed.ai_extracted, "notes": parsed.notes, "clarifications": clarifications,
        "issues": issues, "errors": sum(1 for i in issues if i["severity"] == "error"), "warnings": sum(1 for i in issues if i["severity"] == "warning"),
        "entries": [e.as_dict() for e in result.entries], "diff": diff, "affected_bookings": affected_bookings(session, result.entries, diff),
        "ready_to_import": not clarifications and not any(i["severity"] == "error" for i in issues) and bool(result.entries),
    }
    return summary


def upload(session: Session, user: t.User, filename: str, content: bytes) -> dict:
    if len(content) > MAX_UPLOAD_BYTES:
        raise BadRequest("The file is larger than 8 MB")
    fmt = detect_format(filename, content)
    now = get_now(session)
    job = t.Job(kind="timetable_import", status="PARSING", created_by=user.id, created_at=now, payload={"filename": filename, "format": fmt, "content_b64": base64.b64encode(content).decode(), "answers": {}})
    session.add(job)
    session.flush()
    job.result = run_pipeline(session, job)
    job.status = "READY" if job.result["ready_to_import"] else "NEEDS_ATTENTION"
    term = session.exec(select(t.Term)).first()
    version = t.TimetableVersion(term_id=term.id, source_file=filename, format=fmt, status="DRAFT", issues_json=job.result["issues"], uploaded_by=user.id, created_at=now)
    session.add(version)
    session.flush()
    job.payload = {**job.payload, "version_id": version.id}
    session.add(job)
    audit.append(session, user.email, "timetable.uploaded", {"job_id": job.id, "filename": filename, "format": fmt, "rows": job.result["rows"], "errors": job.result["errors"]})
    session.commit()
    return preview(session, job.id)


def get_job(session: Session, job_id: int) -> t.Job:
    job = session.get(t.Job, job_id)
    if job is None or job.kind != "timetable_import":
        raise NotFound("Timetable job not found")
    return job


def preview(session: Session, job_id: int) -> dict:
    job = get_job(session, job_id)
    body = {k: v for k, v in job.result.items() if k != "entries"}
    body["entries_preview"] = job.result.get("entries", [])[:60]
    return {"job_id": job.id, "status": job.status, "filename": job.payload["filename"], **body}


def answer(session: Session, user: t.User, job_id: int, answers: dict[str, str]) -> dict:
    job = get_job(session, job_id)
    if job.status == "IMPORTED":
        raise Conflict("This timetable was already imported")
    job.payload = {**job.payload, "answers": {**job.payload.get("answers", {}), **answers}}
    job.result = run_pipeline(session, job)
    job.status = "READY" if job.result["ready_to_import"] else "NEEDS_ATTENTION"
    session.add(job)
    audit.append(session, user.email, "timetable.clarified", {"job_id": job.id, "answers": answers})
    session.commit()
    return preview(session, job_id)


def import_job(session: Session, user: t.User, job_id: int) -> dict:
    job = get_job(session, job_id)
    if job.status == "IMPORTED":
        raise Conflict("This timetable was already imported")
    result = run_pipeline(session, job)
    if not result["ready_to_import"]:
        raise Conflict("The timetable still has open questions or errors", {"errors": result["errors"], "clarifications": result["clarifications"], "issues": result["issues"]})
    entries = [NormalisedEntry(**e) for e in result["entries"]]
    sections = {e.section_id for e in entries}
    previous = active_version(session)
    version = session.get(t.TimetableVersion, job.payload["version_id"])
    term = session.get(t.Term, version.term_id)
    kept = [e for e in session.exec(select(t.TimetableEntry).where(t.TimetableEntry.version_id == previous.id)) if e.section_id not in sections] if previous else []
    new_rows: list[t.TimetableEntry] = []
    for old in kept:
        new_rows.append(t.TimetableEntry(version_id=version.id, section_id=old.section_id, course_code=old.course_code, course_name=old.course_name, faculty_id=old.faculty_id, venue_id=old.venue_id, weekday=old.weekday, start_min=old.start_min, end_min=old.end_min, kind=old.kind, effective_from=old.effective_from, effective_to=old.effective_to))
    for entry in entries:
        new_rows.append(t.TimetableEntry(version_id=version.id, section_id=entry.section_id, course_code=entry.course_code, course_name=entry.course_name, faculty_id=entry.faculty_id, venue_id=entry.venue_id, weekday=entry.weekday, start_min=entry.start_min, end_min=entry.end_min, kind=entry.kind, effective_from=term.start, effective_to=term.end))
    session.add_all(new_rows)
    session.flush()
    by_key = {(r.section_id, r.weekday, r.start_min, r.course_code, r.venue_id): r for r in new_rows}
    carried = 0
    if previous:
        old_entries = {e.id: e for e in session.exec(select(t.TimetableEntry).where(t.TimetableEntry.version_id == previous.id))}
        for exception in list(session.exec(select(t.ScheduleException))):
            old = old_entries.get(exception.entry_id)
            if old is None:
                continue
            twin = by_key.get((old.section_id, old.weekday, old.start_min, old.course_code, old.venue_id))
            if twin is not None:
                session.add(t.ScheduleException(entry_id=twin.id, date=exception.date, type=exception.type, reason=exception.reason, status=exception.status, created_by=exception.created_by, venue_id=exception.venue_id, start_min=exception.start_min, end_min=exception.end_min))
                carried += 1
        previous.status = "ARCHIVED"
        session.add(previous)
    version.status = "ACTIVE"
    version.issues_json = result["issues"]
    session.add(version)
    job.status = "IMPORTED"
    job.result = {**job.result, "imported_version_id": version.id}
    session.add(job)
    audit.append(session, user.email, "timetable.imported", {"job_id": job.id, "version_id": version.id, "entries": len(entries), "sections": sorted(sections), "previous_version_id": previous.id if previous else None, "exceptions_carried": carried})
    session.commit()
    return {"job_id": job.id, "version_id": version.id, "status": "ACTIVE", "entries_imported": len(entries), "previous_version_id": previous.id if previous else None}


def list_versions(session: Session) -> list[dict]:
    counts: dict[int, int] = defaultdict(int)
    for entry in session.exec(select(t.TimetableEntry)):
        counts[entry.version_id] += 1
    return [
        {"id": v.id, "source_file": v.source_file, "format": v.format, "status": v.status, "created_at": v.created_at.isoformat(), "entries": counts.get(v.id, 0), "errors": sum(1 for i in v.issues_json if i.get("severity") == "error")}
        for v in session.exec(select(t.TimetableVersion).order_by(t.TimetableVersion.id.desc()))
    ]


def rollback(session: Session, user: t.User, version_id: int) -> dict:
    target = session.get(t.TimetableVersion, version_id)
    if target is None:
        raise NotFound("Version not found")
    if target.status != "ARCHIVED":
        raise Conflict(f"Only an archived version can be restored; this one is {target.status}")
    current = active_version(session)
    if current:
        current.status = "ARCHIVED"
        session.add(current)
    target.status = "ACTIVE"
    session.add(target)
    audit.append(session, user.email, "timetable.rolled_back", {"restored": target.id, "replaced": current.id if current else None})
    session.commit()
    return {"restored_version_id": target.id, "status": "ACTIVE"}
