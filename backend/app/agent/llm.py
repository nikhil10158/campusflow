import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app import db
from app.config import get_settings
from app.models.tables import LLMUsage

BREAKER_FAILURES = 3
BREAKER_SECONDS = 60
MAX_WAIT_SECONDS = 8
CACHE_LIMIT = 200


class LLMUnavailable(Exception):
    pass


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    parts: list[Any] = field(default_factory=list)


class TokenBucket:
    def __init__(self, per_minute: int) -> None:
        self.capacity = max(1, per_minute)
        self.tokens = float(self.capacity)
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def take(self, wait_up_to: float) -> bool:
        deadline = time.monotonic() + wait_up_to
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.capacity / 60)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)


class LLM:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.bucket = TokenBucket(self.settings.llm_rpm)
        self.failures = 0
        self.open_until = 0.0
        self.cache: dict[str, LLMResult] = {}
        self.client: Any = None
        self.last_error = ""

    def configured(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def breaker_open(self) -> bool:
        return time.monotonic() < self.open_until

    def calls_today(self) -> int:
        with db.session_scope() as session:
            rows = session.exec(select(LLMUsage).where(LLMUsage.day == date.today())).all()
            return sum(r.calls for r in rows)

    def status(self) -> dict:
        used = self.calls_today() if self.configured() else 0
        remaining = max(0, self.settings.llm_rpd - used)
        if not self.configured():
            mode = "offline"
        elif self.breaker_open() or remaining == 0:
            mode = "degraded"
        else:
            mode = "live"
        return {"mode": mode, "model": self.settings.gemini_model if self.configured() else None, "calls_today": used, "remaining_est": remaining if self.configured() else 0, "daily_limit": self.settings.llm_rpd, "last_error": self.last_error}

    def usable(self) -> bool:
        return self.configured() and not self.breaker_open() and self.calls_today() < self.settings.llm_rpd

    def record_call(self, model: str) -> None:
        with db.session_scope(write=True) as session:
            row = session.exec(select(LLMUsage).where(LLMUsage.day == date.today(), LLMUsage.model == model)).first()
            if row is None:
                row = LLMUsage(day=date.today(), model=model, calls=0)
            row.calls += 1
            session.add(row)
            session.commit()

    def sdk(self) -> Any:
        if self.client is None:
            from google import genai

            self.client = genai.Client(api_key=self.settings.gemini_api_key)
        return self.client

    def models(self) -> list[str]:
        return [self.settings.gemini_model, *self.settings.gemini_fallback_models]

    def generate(
        self, contents: Any, system: str | None = None, tools: list[dict] | None = None, response_schema: dict | None = None,
        cache: bool = False, force_tool: bool = False,
    ) -> LLMResult:
        if not self.usable():
            raise LLMUnavailable("Gemini is not available (no key, quota used up or circuit open)")
        key = hashlib.sha256(json.dumps([str(contents), system, tools, response_schema], sort_keys=True, default=str).encode()).hexdigest()
        if cache and key in self.cache:
            return self.cache[key]
        last: Exception | None = None
        for model in self.models():
            try:
                result = self.call_model(model, contents, system, tools, response_schema, force_tool)
            except LLMUnavailable as error:
                last = error
                continue
            self.failures = 0
            if cache:
                if len(self.cache) >= CACHE_LIMIT:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = result
            return result
        self.failures += 1
        if self.failures >= BREAKER_FAILURES:
            self.open_until = time.monotonic() + BREAKER_SECONDS
            self.failures = 0
        self.last_error = str(last) if last else "unknown failure"
        raise LLMUnavailable(self.last_error)

    def call_model(self, model: str, contents: Any, system: str | None, tools: list[dict] | None, response_schema: dict | None, force_tool: bool) -> LLMResult:
        from google.genai import types

        config: dict[str, Any] = {"temperature": 0.0}
        if system:
            config["system_instruction"] = system
        if tools:
            declarations = [types.FunctionDeclaration(name=t["name"], description=t["description"], parameters_json_schema=t["parameters"]) for t in tools]
            config["tools"] = [types.Tool(function_declarations=declarations)]
            config["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
            if force_tool:
                config["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY"))
        if response_schema:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = response_schema
        for attempt in range(2):
            if not self.bucket.take(MAX_WAIT_SECONDS):
                raise LLMUnavailable("Rate limit reached for this minute")
            try:
                self.record_call(model)
                response = self.sdk().models.generate_content(model=model, contents=contents, config=types.GenerateContentConfig(**config))
                return self.read(response, model)
            except Exception as error:
                message = str(error)
                self.last_error = message[:300]
                delay = retry_delay(message)
                if "429" in message or "RESOURCE_EXHAUSTED" in message:
                    if delay is not None and delay <= MAX_WAIT_SECONDS and attempt == 0:
                        time.sleep(delay)
                        continue
                    raise LLMUnavailable(f"{model} is out of quota")
                raise LLMUnavailable(f"{model} failed: {message[:200]}")
        raise LLMUnavailable(f"{model} kept failing")

    def read(self, response: Any, model: str) -> LLMResult:
        result = LLMResult(model=model)
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            return result
        result.parts = list(candidate.content.parts or [])
        for part in result.parts:
            if getattr(part, "function_call", None):
                result.tool_calls.append(ToolCall(part.function_call.name, dict(part.function_call.args or {})))
            elif getattr(part, "text", None):
                result.text += part.text
        return result

    def stream_text(self, contents: Any, system: str | None = None):
        from google.genai import types

        if not self.usable():
            raise LLMUnavailable("Gemini is not available")
        model = self.models()[0]
        if not self.bucket.take(MAX_WAIT_SECONDS):
            raise LLMUnavailable("Rate limit reached for this minute")
        self.record_call(model)
        config = types.GenerateContentConfig(temperature=0.0, system_instruction=system) if system else types.GenerateContentConfig(temperature=0.0)
        try:
            for chunk in self.sdk().models.generate_content_stream(model=model, contents=contents, config=config):
                if chunk.text:
                    yield chunk.text
        except Exception as error:
            self.last_error = str(error)[:300]
            raise LLMUnavailable(str(error)[:200])


def retry_delay(message: str) -> float | None:
    match = re.search(r"retry in ([\d.]+)s", message, flags=re.IGNORECASE) or re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)s", message)
    return float(match.group(1)) if match else None


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm


def reset_llm() -> None:
    global _llm
    _llm = None
