from __future__ import annotations

import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.auth.security import decode_access_token
from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


def get_authenticated_album_key(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        try:
            payload = decode_access_token(authorization.split(" ", 1)[1])
            subject = payload.get("sub")
            if subject:
                album_id = request.path_params.get("album_id") or "unknown"
                return f"user:{subject}:album:{album_id}"
        except Exception:  # noqa: BLE001
            pass
    return f"ip:{get_remote_address(request)}"


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
    response = JSONResponse(
        status_code=429,
        content={
            "code": 429,
            "message": "too many requests",
            "request_id": request_id,
            "data": None,
        },
    )
    current_limit = getattr(request.state, "view_rate_limit", None)
    if current_limit is not None:
        limit_item, scope = current_limit
        reset_at, remaining = limiter.limiter.get_window_stats(limit_item, *scope)
        retry_after = max(0, int(reset_at - time.time()) + 1)
        response.headers["X-RateLimit-Limit"] = str(limit_item.amount)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(reset_at))
        response.headers["Retry-After"] = str(retry_after)
    return response
