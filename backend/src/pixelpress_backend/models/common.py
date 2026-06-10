from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BaseSchema(BaseModel):
    model_config = {
        "populate_by_name": True,
        "extra": "forbid",
    }


class Actor(BaseSchema):
    type: str = Field(default="user")
    id: str


class ErrorInfo(BaseSchema):
    code: str
    message: str


class AuditMeta(BaseSchema):
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class IdentifiedModel(BaseSchema):
    id: str = Field(default_factory=lambda: str(uuid4()))


JSONDict = dict[str, Any]
