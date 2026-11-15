import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text
from sqlmodel import Session

from app import db
from app.services import audit

source = Path(os.environ.get("TAMPER_DB", ROOT / "backend" / "campusflow.db"))
if not source.exists():
    sys.exit(f"No database at {source}; run make seed first")

work = Path(tempfile.mkdtemp()) / "tampered.db"
shutil.copy(source, work)
engine = db.configure(f"sqlite:///{work.as_posix()}")

with Session(engine) as session:
    print("before tampering:", audit.verify(session))

with engine.begin() as connection:
    row = connection.execute(text("SELECT id FROM auditlog ORDER BY id LIMIT 1 OFFSET 3")).scalar()
    connection.execute(text("DROP TRIGGER auditlog_no_update"))
    connection.execute(text("UPDATE auditlog SET actor = 'mallory' WHERE id = :id"), {"id": row})

with Session(engine) as session:
    verdict = audit.verify(session)
print(f"edited row #{row}; after tampering:", verdict)
print("chain turned red at the edited row" if not verdict["ok"] and verdict["broken_at"] == row else "unexpected result")
