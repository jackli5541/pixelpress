from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.request_context import get_request_context

_RESERVED_LOG_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(get_request_context())
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_KEYS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_request_context().items():
            setattr(record, key, value)
        return True


def setup_logging(*, level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    formatter = JsonFormatter()

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.addFilter(ContextFilter())
        root.addHandler(handler)
        return

    for handler in root.handlers:
        handler.setFormatter(formatter)
        has_filter = any(isinstance(item, ContextFilter) for item in handler.filters)
        if not has_filter:
            handler.addFilter(ContextFilter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
