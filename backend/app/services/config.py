from app.config import get_settings


def solver_settings() -> dict:
    settings = get_settings()
    return {"time_limit": settings.solver_time_limit_s, "workers": settings.solver_workers}
