from __future__ import annotations

import math
import time
from typing import Any

import httpx

from app.ai.types import (
    ImageEmbeddingRequest,
    ImageEmbeddingResponse,
    TextEmbeddingRequest,
    TextEmbeddingResponse,
)
from app.core.config import get_settings


class EmbeddingProviderError(RuntimeError):
    pass


class DashScopeMultimodalEmbeddingProvider:
    provider_name = "dashscope_multimodal_embedding"
    default_endpoint = (
        "https://dashscope.aliyuncs.com/api/v1/services/embeddings/"
        "multimodal-embedding/multimodal-embedding"
    )

    def __init__(self) -> None:
        settings = get_settings()
        self.timeout_seconds = settings.ai_request_timeout_seconds
        self.max_retries = settings.ai_provider_max_retries

    async def embed_images(self, request: ImageEmbeddingRequest) -> ImageEmbeddingResponse:
        if not request.images:
            raise EmbeddingProviderError("at least one image is required")
        contents = [
            {"image": f"data:{image.media_type};base64,{image.data_base64}"}
            for image in request.images
        ]
        embeddings, metadata = await self._embed_contents(
            contents,
            model=request.model,
            dimension=request.dimension,
            connection=request.connection,
        )
        return ImageEmbeddingResponse(embeddings=embeddings, **metadata)

    async def embed_texts(self, request: TextEmbeddingRequest) -> TextEmbeddingResponse:
        texts = [str(value or "").strip() for value in request.texts]
        if not texts or any(not value for value in texts):
            raise EmbeddingProviderError("at least one non-empty text is required")
        embeddings, metadata = await self._embed_contents(
            [{"text": value} for value in texts],
            model=request.model,
            dimension=request.dimension,
            connection=request.connection,
        )
        return TextEmbeddingResponse(embeddings=embeddings, **metadata)

    async def _embed_contents(self, contents, *, model, dimension, connection):  # noqa: ANN001
        api_key = connection.api_key if connection else None
        endpoint = (connection.api_url if connection else None) or self.default_endpoint
        resolved_model = (connection.model if connection else None) or model
        if not api_key:
            raise EmbeddingProviderError("DashScope embedding API is not configured")
        payload = {
            "model": resolved_model,
            "input": {"contents": contents},
            "parameters": {"dimension": dimension},
        }
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started_at = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    response_json = response.json()
                embeddings = self._extract_embeddings(response_json, len(contents), dimension)
                return embeddings, {
                    "model": resolved_model,
                    "provider": self.provider_name,
                    "debug": {
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
                        "request_id": response_json.get("request_id"),
                        "source": connection.source if connection else "settings",
                        "config_id": connection.config_id if connection else None,
                    },
                }
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise EmbeddingProviderError(f"embedding provider request failed: {last_error}") from last_error

    @staticmethod
    def _extract_embeddings(payload: dict[str, Any], expected: int, dimension: int) -> list[list[float]]:
        output = payload.get("output") or {}
        items = output.get("embeddings") or []
        if len(items) != expected:
            raise EmbeddingProviderError("embedding response count mismatch")
        vectors: list[list[float]] = []
        for item in sorted(items, key=lambda value: int(value.get("index", 0))):
            raw = item.get("embedding")
            if not isinstance(raw, list) or len(raw) != dimension:
                raise EmbeddingProviderError("embedding response dimension mismatch")
            vector = [float(value) for value in raw]
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingProviderError("embedding response contains non-finite values")
            norm = math.sqrt(sum(value * value for value in vector))
            if norm <= 0:
                raise EmbeddingProviderError("embedding response contains a zero vector")
            vectors.append([value / norm for value in vector])
        return vectors
