"""Pure-ASGI middleware: request ids, security headers, access logging, body limits."""

from __future__ import annotations

import json
import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import AppError, error_body

logger = logging.getLogger("imageproof")

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"no-referrer",
    b"x-frame-options": b"DENY",
    b"cross-origin-resource-policy": b"same-site",
}


class RequestContextMiddleware:
    """Adds X-Request-ID, security headers and Cache-Control: no-store; logs one line per request.

    Log lines contain method, path, status and duration only. File names, image
    content and extracted metadata are never logged.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_holder = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}
                headers.append((b"x-request-id", request_id.encode()))
                for key, value in SECURITY_HEADERS.items():
                    if key not in existing:
                        headers.append((key, value))
                if scope["path"].startswith("/api/") and b"cache-control" not in existing:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if scope["path"] != "/api/v1/health":
                logger.info(
                    "request id=%s method=%s path=%s status=%s duration_ms=%d",
                    request_id,
                    scope["method"],
                    scope["path"],
                    status_holder["status"],
                    int((time.perf_counter() - started) * 1000),
                )


class BodySizeLimitMiddleware:
    """Rejects oversized request bodies while streaming, before they are buffered.

    The multipart parser would otherwise buffer an entire upload before any
    handler code runs, so the limit has to be enforced at the ASGI layer.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int, path_prefix: str = "/api/v1/analyze") -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].startswith(self.path_prefix)
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > self.max_body_bytes
            except ValueError:
                too_big = False
            if too_big:
                await self._reject(scope, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise self._error()
            return message

        await self.app(scope, limited_receive, send)

    def _error(self) -> AppError:
        limit_mb = round(self.max_body_bytes / (1024 * 1024), 1)
        return AppError(
            413,
            "file_too_large",
            f"The upload exceeds the maximum size of about {limit_mb} MB.",
            details={"max_bytes": self.max_body_bytes},
        )

    async def _reject(self, scope: Scope, send: Send) -> None:
        err = self._error()
        body = json.dumps(
            error_body(err.code, err.message, scope.get("state", {}).get("request_id"), err.details)
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
