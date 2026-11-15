from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, event, text
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings
from app.models import tables

AUDIT_TRIGGERS_SQLITE = [
    "CREATE TRIGGER IF NOT EXISTS auditlog_no_update BEFORE UPDATE ON auditlog BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS auditlog_no_delete BEFORE DELETE ON auditlog BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END",
]

AUDIT_TRIGGERS_POSTGRES = [
    "CREATE OR REPLACE FUNCTION auditlog_block() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'audit log is append-only'; END; $$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS auditlog_no_change ON auditlog",
    "CREATE TRIGGER auditlog_no_change BEFORE UPDATE OR DELETE ON auditlog FOR EACH ROW EXECUTE FUNCTION auditlog_block()",
]


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 60}, poolclass=NullPool)

        @event.listens_for(engine, "connect")
        def on_connect(dbapi_connection, _record) -> None:
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=60000")
            cursor.close()

        @event.listens_for(engine, "begin")
        def on_begin(connection) -> None:
            mode = "IMMEDIATE" if connection.get_execution_options().get("immediate") else "DEFERRED"
            connection.exec_driver_sql(f"BEGIN {mode}")

        return engine
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


_engine: Engine | None = None


def configure(url: str | None = None) -> Engine:
    global _engine
    _engine = make_engine(url or get_settings().database_url)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        configure()
    assert _engine is not None
    return _engine


def create_schema(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    statements = AUDIT_TRIGGERS_SQLITE if engine.dialect.name == "sqlite" else AUDIT_TRIGGERS_POSTGRES
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def drop_schema(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            for statement in ("DROP TRIGGER IF EXISTS auditlog_no_update", "DROP TRIGGER IF EXISTS auditlog_no_delete"):
                connection.execute(text(statement))
    else:
        with engine.begin() as connection:
            connection.execute(text("DROP TRIGGER IF EXISTS auditlog_no_change ON auditlog"))
    SQLModel.metadata.drop_all(engine)


def open_session(write: bool = False) -> Session:
    session = Session(get_engine())
    if write:
        session.connection(execution_options={"immediate": True})
    return session


def begin_immediate(session: Session) -> None:
    session.rollback()
    session.connection(execution_options={"immediate": True})


def get_session() -> Iterator[Session]:
    with open_session() as session:
        yield session


@contextmanager
def session_scope(write: bool = False) -> Iterator[Session]:
    with open_session(write) as session:
        yield session


def lock_resource(session: Session, resource_type: str, resource_id: int) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    table = {"venue": tables.Venue, "guest_room": tables.GuestRoom, "parking": tables.ParkingLot}[resource_type]
    session.query(table).filter(table.id == resource_id).with_for_update().first()
