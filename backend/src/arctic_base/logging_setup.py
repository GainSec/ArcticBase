"""Structured JSON logging to stdout. Request IDs propagated via contextvar."""

from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from collections import deque
from typing import TypedDict

from starlette.requests import Request
from starlette.types import ASGIApp

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class ActivityRecord(TypedDict):
    ts: float
    method: str
    path: str
    status: int
    elapsed_ms: float
    request_id: str
    is_agent: bool


# In-memory ring buffer of the last N requests. Single-process, single-user — no need for redis.
_ACTIVITY: deque[ActivityRecord] = deque(maxlen=200)


def get_recent_activity(limit: int = 100, agent_only: bool = False) -> list[ActivityRecord]:
    items = list(_ACTIVITY)
    if agent_only:
        items = [r for r in items if r["is_agent"]]
    return items[-limit:][::-1]  # newest first


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": _request_id.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # quiet uvicorn's default access log; we emit our own
    logging.getLogger("uvicorn.access").propagate = False


class RequestIdMiddleware:
    """ASGI middleware that assigns/forwards a request id and emits one INFO log per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.log = logging.getLogger("arctic_base.http")

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = _request_id.set(rid)
        start = time.perf_counter()
        status_code = {"value": 500}

        async def send_wrapper(message):  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                status_code["value"] = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", rid.encode("ascii")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.log.info(
                "%s %s -> %d (%.1fms)",
                request.method,
                request.url.path,
                status_code["value"],
                elapsed_ms,
            )
            # Record into the in-memory activity buffer (excluding the activity endpoint itself
            # to avoid the dashboard polling it cluttering its own output).
            path = request.url.path
            if path != "/api/agent/activity":
                # An "agent" request is anything that isn't a SPA asset/index serve.
                is_agent = (
                    path.startswith("/api/")
                    or path == "/openapi.json"
                    or path == "/agent"
                    or path == "/docs"
                )
                _ACTIVITY.append(
                    ActivityRecord(
                        ts=time.time(),
                        method=request.method,
                        path=path,
                        status=status_code["value"],
                        elapsed_ms=round(elapsed_ms, 1),
                        request_id=rid,
                        is_agent=is_agent,
                    )
                )
            _request_id.reset(token)


__all__ = ["configure_logging", "RequestIdMiddleware"]
