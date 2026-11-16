import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app import db
from app.api import admin, agent, auth, availability, bookings, exports, reference, reports, resources, timetables
from app.config import get_settings
from app.seed import load
from app.services.errors import ServiceError

logger = logging.getLogger("campusflow")


class ErrorGuard:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked(message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception:
            logger.exception("Unhandled error on %s", scope.get("path"))
            if started:
                raise
            await JSONResponse({"detail": "Internal server error"}, status_code=500)(scope, receive, send)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.create_schema()
    if get_settings().auto_seed_on_empty:
        load.ensure_seeded()
    with Session(db.get_engine()) as session:
        db.reset_sequences(session)
        session.commit()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CampusFlow API", version="0.1.0", description="SYNTHETIC DATA ONLY - JKLU-like demo campus", lifespan=lifespan)
    app.add_middleware(ErrorGuard)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.frontend_origins, allow_origin_regex=settings.frontend_origin_regex,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )

    @app.exception_handler(ServiceError)
    async def service_error_handler(_request: Request, error: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.message, **error.data})

    for module in (admin, agent, auth, availability, bookings, exports, reference, reports, resources, timetables):
        app.include_router(module.router)
    return app


app = create_app()
