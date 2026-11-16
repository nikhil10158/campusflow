import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("CAMPUSFLOW_DATA_DIR", ROOT_DIR / "data"))
if not DATA_DIR.exists():
    DATA_DIR = Path("/app/data")

load_dotenv(BACKEND_DIR / ".env")


def normalise_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    pass_secret: str
    demo_now: datetime
    frontend_origins: list[str]
    frontend_origin_regex: str | None
    gemini_api_key: str
    gemini_model: str
    gemini_fallback_models: list[str]
    llm_rpm: int
    llm_rpd: int
    solver_workers: int
    solver_time_limit_s: float
    auto_seed_on_empty: bool


def build_settings() -> Settings:
    cpus = os.cpu_count() or 1
    workers = int(os.environ.get("SOLVER_WORKERS", min(8, cpus) if cpus > 1 else 2))
    default_limit = 10.0 if cpus > 1 else 5.0
    default_db = f"sqlite:///{(BACKEND_DIR / 'campusflow.db').as_posix()}"
    return Settings(
        database_url=normalise_database_url(os.environ.get("DATABASE_URL", default_db)),
        jwt_secret=os.environ.get("JWT_SECRET", "dev-secret-change-me-dev-secret-change-me"),
        pass_secret=os.environ.get("PASS_SECRET", os.environ.get("JWT_SECRET", "dev-pass-secret")),
        demo_now=datetime.fromisoformat(os.environ.get("DEMO_NOW", "2026-11-16T10:00:00")),
        frontend_origins=[o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
        frontend_origin_regex=os.environ.get("FRONTEND_ORIGIN_REGEX") or r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        gemini_fallback_models=[m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()],
        llm_rpm=int(os.environ.get("LLM_RPM", "10")),
        llm_rpd=int(os.environ.get("LLM_RPD", "400")),
        solver_workers=workers,
        solver_time_limit_s=float(os.environ.get("SOLVER_TIME_LIMIT_S", default_limit)),
        auto_seed_on_empty=os.environ.get("AUTO_SEED_ON_EMPTY", "true").lower() == "true",
    )


@lru_cache
def get_settings() -> Settings:
    return build_settings()
