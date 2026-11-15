from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.deps import AdminUser, SessionDep
from app.seed.files import SAMPLE_DIR
from app.services import timetables

router = APIRouter(prefix="/timetables", tags=["timetables"])


class AnswerIn(BaseModel):
    answers: dict[str, str]


@router.post("/upload")
async def upload(session: SessionDep, user: AdminUser, file: UploadFile = File(...)) -> dict:
    content = await file.read()
    return timetables.upload(session, user, file.filename or "upload", content)


@router.get("/samples")
def samples(user: AdminUser) -> list[dict]:
    return [{"name": p.name, "size": p.stat().st_size} for p in sorted(SAMPLE_DIR.glob("*")) if p.is_file()]


@router.get("/samples/{name}")
def sample_file(name: str, user: AdminUser) -> FileResponse:
    target = (SAMPLE_DIR / name).resolve()
    if SAMPLE_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="No such sample file")
    return FileResponse(target, filename=target.name)


@router.get("/versions")
def versions(session: SessionDep, user: AdminUser) -> list[dict]:
    return timetables.list_versions(session)


@router.post("/versions/{version_id}/rollback")
def rollback(version_id: int, session: SessionDep, user: AdminUser) -> dict:
    return timetables.rollback(session, user, version_id)


@router.get("/{job_id}/preview")
def preview(job_id: int, session: SessionDep, user: AdminUser) -> dict:
    return timetables.preview(session, job_id)


@router.post("/{job_id}/answer")
def answer(job_id: int, payload: AnswerIn, session: SessionDep, user: AdminUser) -> dict:
    return timetables.answer(session, user, job_id, payload.answers)


@router.post("/{job_id}/import")
def import_job(job_id: int, session: SessionDep, user: AdminUser) -> dict:
    return timetables.import_job(session, user, job_id)
