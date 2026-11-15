import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from collections.abc import Iterator

from app.db import open_session
from app.models.tables import User
from app.services import auth

bearer = HTTPBearer(auto_error=False)


def request_session(request: Request) -> Iterator[Session]:
    with open_session(write=request.method != "GET") as session:
        yield session


SessionDep = Annotated[Session, Depends(request_session)]
hits: dict[str, deque[float]] = defaultdict(deque)


def current_user(session: SessionDep, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in first")
    user_id = auth.decode_token(credentials.credentials)
    user = session.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: str) -> Callable[[User], User]:
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires one of: {', '.join(roles)}")
        return user

    return check


def rate_limit(name: str, limit: int, per_seconds: int) -> Callable[[Request], None]:
    def check(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        key = f"{name}:{client}"
        now = time.monotonic()
        window = hits[key]
        while window and now - window[0] > per_seconds:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests, slow down")
        window.append(now)

    return check


def reset_rate_limits() -> None:
    hits.clear()


AdminUser = Annotated[User, Depends(require_roles("admin"))]
