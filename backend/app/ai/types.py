from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderConnectionConfig:
    provider: str
    api_key: str | None
    api_url: str | None
    model: str
    source: str
    config_id: str | None = None
    project_id: str | None = None


@dataclass(slots=True)
class ImagePayload:
    media_type: str
    data_base64: str
    width: int | None = None
    height: int | None = None
    filename: str | None = None


@dataclass(slots=True)
class ProviderRequest:
    system_prompt: str
    user_prompt: str
    output_schema: dict[str, Any]
    model: str
    response_temperature: float = 0.2
    images: list[ImagePayload] = field(default_factory=list)
    connection: ProviderConnectionConfig | None = None


@dataclass(slots=True)
class ProviderResponse:
    payload: dict[str, Any]
    raw_text: str
    model: str
    provider: str
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ImageEmbeddingRequest:
    images: list[ImagePayload]
    model: str
    dimension: int = 512
    connection: ProviderConnectionConfig | None = None


@dataclass(slots=True)
class ImageEmbeddingResponse:
    embeddings: list[list[float]]
    model: str
    provider: str
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TextEmbeddingRequest:
    texts: list[str]
    model: str
    dimension: int = 512
    connection: ProviderConnectionConfig | None = None


@dataclass(slots=True)
class TextEmbeddingResponse:
    embeddings: list[list[float]]
    model: str
    provider: str
    debug: dict[str, Any] = field(default_factory=dict)
