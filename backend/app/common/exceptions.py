from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.observability import apply_sentry_context
from app.core.request_context import get_request_context, get_request_id

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = get_request_id() or "unknown"
    logger.warning(
        "request failed",
        extra={
            "event": "http.request.failed",
            "status_code": exc.status_code,
            "detail": exc.detail,
            "request_id": request_id,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": exc.detail if isinstance(exc.detail, str) else "request failed",
            "request_id": request_id,
            "data": exc.detail if not isinstance(exc.detail, str) else None,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = get_request_id() or "unknown"
    logger.warning(
        "request validation failed",
        extra={
            "event": "http.request.failed",
            "status_code": 422,
            "errors": exc.errors(),
            "request_id": request_id,
        },
    )
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "request validation failed",
            "request_id": request_id,
            "data": exc.errors(),
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = get_request_id() or "unknown"
    apply_sentry_context()
    logger.exception(
        "unhandled request exception",
        extra={
            "event": "http.request.failed",
            "status_code": 500,
            "request_id": request_id,
            "context": get_request_context(),
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "internal server error",
            "request_id": request_id,
            "data": None,
        },
    )
