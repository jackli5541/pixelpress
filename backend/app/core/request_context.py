from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_REQUEST_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("request_context", default={})


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def get_request_context() -> dict[str, Any]:
    return dict(_REQUEST_CONTEXT.get())


def clear_request_context() -> None:
    _REQUEST_CONTEXT.set({})


def bind_request_context(**values: Any) -> dict[str, Any]:
    merged = get_request_context()
    merged.update(_compact(values))
    _REQUEST_CONTEXT.set(merged)
    return merged


def replace_request_context(**values: Any) -> dict[str, Any]:
    compacted = _compact(values)
    _REQUEST_CONTEXT.set(compacted)
    return dict(compacted)


def get_request_id() -> str | None:
    value = _REQUEST_CONTEXT.get().get("request_id")
    return value if isinstance(value, str) and value else None
