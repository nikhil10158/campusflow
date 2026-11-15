import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from app.models.tables import AuditLog

GENESIS_HASH = "0" * 64
ADVISORY_LOCK_KEY = 7001


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, ts: datetime, actor: str, action: str, detail: dict) -> str:
    payload = canonical({"ts": ts.isoformat(), "actor": actor, "action": action, "detail": detail})
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


def last_hash(session: Session) -> str:
    latest = session.exec(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
    return latest.hash if latest else GENESIS_HASH


def append(session: Session, actor: str, action: str, detail: dict | None = None) -> AuditLog:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text(f"SELECT pg_advisory_xact_lock({ADVISORY_LOCK_KEY})"))
    clean_detail = json.loads(canonical(detail or {}))
    ts = datetime.now().replace(microsecond=0)
    prev_hash = last_hash(session)
    row = AuditLog(ts=ts, actor=actor, action=action, detail=clean_detail, prev_hash=prev_hash, hash=compute_hash(prev_hash, ts, actor, action, clean_detail))
    session.add(row)
    session.flush()
    return row


def verify(session: Session) -> dict:
    previous = GENESIS_HASH
    checked = 0
    for row in session.exec(select(AuditLog).order_by(AuditLog.id)):
        expected = compute_hash(previous, row.ts, row.actor, row.action, row.detail)
        if row.prev_hash != previous or row.hash != expected:
            return {"ok": False, "checked": checked, "broken_at": row.id}
        previous = row.hash
        checked += 1
    return {"ok": True, "checked": checked, "broken_at": None}
