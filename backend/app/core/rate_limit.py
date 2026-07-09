from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    request_id = get_request_id() or "unknown"
    logger.warning(
        "request rate limited",
        extra={
            "event": "http.rate_limited",
            "request_id": request_id,
            "path": str(request.url.path),
            "method": request.method,
        },
    )
    return JSONResponse(
        status_code=429,
        content={
            "code": 429,
            "message": "too many requests",
            "request_id": request_id,
            "data": None,
        },
    )
