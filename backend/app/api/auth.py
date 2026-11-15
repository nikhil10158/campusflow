from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.deps import CurrentUser, SessionDep, rate_limit
from app.models.schemas import LoginIn, LoginOut, UserOut
from app.models.tables import User
from app.services import audit, auth

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, role=user.role, scopes=user.scopes, dept=user.dept, ref_id=user.ref_id)


@router.post("/login", response_model=LoginOut, dependencies=[Depends(rate_limit("login", 30, 60))])
def login(payload: LoginIn, session: SessionDep) -> LoginOut:
    user = session.exec(select(User).where(User.email == payload.email.lower().strip())).first()
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        audit.append(session, payload.email, "auth.login_failed", {})
        session.commit()
        raise HTTPException(status_code=401, detail="Wrong email or password")
    audit.append(session, user.email, "auth.login", {"role": user.role})
    session.commit()
    return LoginOut(token=auth.create_token(user), user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return user_out(user)


@router.get("/demo-users")
def demo_users(session: SessionDep) -> list[dict]:
    rows = session.exec(select(User).order_by(User.id)).all()
    return [{"email": u.email, "role": u.role, "name": u.name} for u in rows]
