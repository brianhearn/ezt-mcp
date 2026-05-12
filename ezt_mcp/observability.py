"""Logging and timing helpers for EZT MCP.

The server uses standard-library logging so deployment can route logs to systemd,
App Service, OpenTelemetry collectors, or any future structured-log sink without
changing business logic.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


def new_request_id() -> str:
    """Return a short correlation ID suitable for logs and response headers."""
    return uuid4().hex[:16]


@contextmanager
def timed_operation(
    logger_: logging.Logger,
    operation: str,
    **fields: Any,
) -> Iterator[None]:
    """Log start/completion/failure for a synchronous operation with elapsed ms."""
    start = time.perf_counter()
    logger_.info("%s.start %s", operation, _format_fields(fields))
    try:
        yield
    except Exception as exc:
        elapsed_ms = _elapsed_ms(start)
        logger_.exception(
            "%s.exception elapsed_ms=%.3f exception_type=%s %s",
            operation,
            elapsed_ms,
            exc.__class__.__name__,
            _format_fields(fields),
        )
        raise
    else:
        elapsed_ms = _elapsed_ms(start)
        logger_.info(
            "%s.complete elapsed_ms=%.3f %s",
            operation,
            elapsed_ms,
            _format_fields(fields),
        )


@asynccontextmanager
async def timed_async_operation(
    logger_: logging.Logger,
    operation: str,
    **fields: Any,
) -> AsyncIterator[None]:
    """Log start/completion/failure for an async operation with elapsed ms."""
    start = time.perf_counter()
    logger_.info("%s.start %s", operation, _format_fields(fields))
    try:
        yield
    except Exception as exc:
        elapsed_ms = _elapsed_ms(start)
        logger_.exception(
            "%s.exception elapsed_ms=%.3f exception_type=%s %s",
            operation,
            elapsed_ms,
            exc.__class__.__name__,
            _format_fields(fields),
        )
        raise
    else:
        elapsed_ms = _elapsed_ms(start)
        logger_.info(
            "%s.complete elapsed_ms=%.3f %s",
            operation,
            elapsed_ms,
            _format_fields(fields),
        )


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log total HTTP call time and attach a request ID to each response."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = request.headers.get("x-request-id") or new_request_id()
        start = time.perf_counter()
        fields = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }
        logger.info("http.request.start %s", _format_fields(fields))
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = _elapsed_ms(start)
            logger.exception(
                "http.request.exception elapsed_ms=%.3f exception_type=%s %s",
                elapsed_ms,
                exc.__class__.__name__,
                _format_fields(fields),
            )
            raise

        elapsed_ms = _elapsed_ms(start)
        response.headers["x-request-id"] = request_id
        response.headers["server-timing"] = f"total;dur={elapsed_ms:.3f}"
        logger.info(
            "http.request.complete elapsed_ms=%.3f status_code=%s %s",
            elapsed_ms,
            response.status_code,
            _format_fields(fields),
        )
        return response


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def _format_fields(fields: Mapping[str, Any]) -> str:
    if not fields:
        return ""
    return " ".join(f"{key}={_safe_log_value(value)}" for key, value in fields.items())


def _safe_log_value(value: Any) -> str:
    text = str(value).replace("\n", "\\n")
    # Keep logs readable and avoid accidentally emitting huge payload fragments.
    if len(text) > 240:
        text = text[:237] + "..."
    return text
