import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.router import api_router
from app.common.exceptions import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from app.common.responses import success_response
from app.core.config import get_settings
from app.core.observability import apply_sentry_context, configure_observability, configure_sentry
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.request_context import bind_request_context, clear_request_context, replace_request_context

settings = get_settings()
configure_observability(service_name="backend", log_level=settings.observability_log_level, json_logs=settings.observability_json_logs)
configure_sentry(
    dsn=settings.sentry_dsn,
    environment=settings.sentry_environment or settings.app_env,
    traces_sample_rate=settings.sentry_traces_sample_rate,
    service_name="backend",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI 相册书自动排版系统后端骨架",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_middleware(SlowAPIMiddleware)

cors_allow_origins = settings.resolved_cors_allow_origins
if cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
    replace_request_context(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        album_id=request.path_params.get("album_id"),
        task_id=request.path_params.get("task_id"),
    )
    apply_sentry_context()
    started = perf_counter()
    logger.info("request started", extra={"event": "http.request.started"})
    response = await call_next(request)
    duration_ms = round((perf_counter() - started) * 1000)
    bind_request_context(duration_ms=duration_ms)
    logger.info(
        "request completed",
        extra={
            "event": "http.request.completed",
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    response.headers["X-Request-ID"] = request_id
    clear_request_context()
    return response


@app.get("/")
def root() -> dict:
    return success_response(
        {
            "app": settings.app_name,
            "env": settings.app_env,
        }
    )


app.include_router(api_router)
