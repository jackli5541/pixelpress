from __future__ import annotations

import logging

from sentry_sdk import set_context, set_tag
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

import sentry_sdk

from app.core.logging import setup_logging
from app.core.request_context import get_request_context


def configure_observability(*, service_name: str, log_level: str, json_logs: bool = True) -> None:
    if json_logs:
        setup_logging(level=log_level)
    else:
        logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    logging.getLogger(__name__).info("observability configured", extra={"event": "observability.configured", "service": service_name})


def configure_sentry(*, dsn: str | None, environment: str, traces_sample_rate: float, service_name: str) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    set_tag("service", service_name)
    set_tag("environment", environment)


def apply_sentry_context() -> None:
    context = get_request_context()
    if not context:
        return
    for key in ("request_id", "task_id", "album_id", "job_id", "worker_name", "task_type", "pipeline_name", "stage"):
        value = context.get(key)
        if value is not None:
            set_tag(key, str(value))
    set_context("request_context", context)
