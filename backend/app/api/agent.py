import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app import db
from app.agent import orchestrator, rag, tools
from app.agent.llm import get_llm
from app.deps import CurrentUser, bearer, rate_limit
from app.models.schemas import AgentChatIn, PolicyAskIn
from app.models.tables import User
from app.rules import load_rules
from app.services import audit, auth
from app.services.clock import get_now
from app.services.snapshot import get_index

router = APIRouter(tags=["agent"])
ME_INTENTS = {"lookup", "policy", "free_rooms"}


def light_user(credentials=Depends(bearer)) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in first")
    user_id = auth.decode_token(credentials.credentials)
    with db.session_scope() as session:
        user = session.get(User, user_id) if user_id else None
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        session.expunge(user)
    return user


AgentUser = Annotated[User, Depends(light_user)]


def compose_message(payload: AgentChatIn) -> str:
    if payload.clarification and payload.clarification.get("original"):
        return f"{payload.clarification['original']} {payload.clarification.get('answer', '')}".strip()
    return payload.message


def run_events(user_id: int, message: str, allowed: set[str] | None = None) -> Iterator[dict]:
    with db.session_scope() as session:
        user = session.get(User, user_id)
        index = get_index(session)
        ctx = tools.ToolContext(session, user, index, load_rules(), get_now(session))
        agent = orchestrator.Agent(ctx, message)
        if allowed is not None:
            intent = orchestrator.parse(message, ctx.now, {v.code for v in index.snapshot.venues}, {b.id: b.name for b in index.snapshot.buildings.values()})
            if intent.kind not in allowed and intent.kind != "injection":
                yield {"type": "answer_delta", "text": "This personal assistant can look up your bookings, free rooms and policies. Use the main Concierge for bookings."}
                yield {"type": "done", "mode": "scoped", "llm_calls": 0, "tool_calls": 0}
                return
        yield from agent.run()


def reject_security(user: User) -> None:
    if user.role == "security":
        raise HTTPException(status_code=403, detail="The planning assistant is not available to the security role")


@router.get("/agent/status")
def status(user: CurrentUser) -> dict:
    return get_llm().status()


@router.post("/agent/chat", dependencies=[Depends(rate_limit("agent", 40, 60))])
def chat(payload: AgentChatIn, user: AgentUser) -> EventSourceResponse:
    reject_security(user)
    message = compose_message(payload)
    if not message.strip():
        raise HTTPException(status_code=422, detail="Say what you need")

    def stream() -> Iterator[dict]:
        for event in run_events(user.id, message):
            yield {"event": event["type"], "data": json.dumps(event, default=str)}

    return EventSourceResponse(stream())


@router.post("/me/chat", dependencies=[Depends(rate_limit("agent", 40, 60))])
def me_chat(payload: AgentChatIn, user: AgentUser) -> dict:
    reject_security(user)
    events = list(run_events(user.id, compose_message(payload), ME_INTENTS))
    return {"events": json.loads(json.dumps(events, default=str)), "answer": "".join(e.get("text", "") for e in events if e["type"] == "answer_delta")}


@router.post("/agent/policies/ask", dependencies=[Depends(rate_limit("agent", 40, 60))])
def ask_policies(payload: PolicyAskIn, user: AgentUser) -> dict:
    answer = rag.ask_policy(payload.question, use_llm=get_llm().usable())
    with db.session_scope(write=True) as session:
        audit.append(session, user.email, "policy.asked", {"question": payload.question[:300], "refused": answer["refused"], "citations": answer["citations"]})
        session.commit()
    return answer
