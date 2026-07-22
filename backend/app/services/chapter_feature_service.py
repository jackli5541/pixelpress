from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_multimodal_embedding_provider
from app.ai.types import ImageEmbeddingRequest, ProviderConnectionConfig
from app.core.config import get_settings
from app.engines.chapter_engine.image_payloads import encode_image_payload
from app.repositories.photo_chapter_feature_repo import PhotoChapterFeatureRepository
from app.services.default_ai_provider_config_service import DefaultAIProviderConfigService
from app.storage.file_store import get_file_storage


class ChapterFeatureService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PhotoChapterFeatureRepository(session)
        self.default_configs = DefaultAIProviderConfigService(session)
        self.storage = get_file_storage()

    async def extract(
        self,
        album_id: str,
        photos: list[Any],
        *,
        progress_callback: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> tuple[dict[str, dict], dict[str, Any]]:
        del album_id
        settings = get_settings()
        connection = await self.resolve_embedding_connection()
        metrics: dict[str, Any] = {
            "cache_hit_count": 0,
            "embedding_success_count": 0,
            "embedding_failure_count": 0,
            "embedding_provider": connection.provider,
            "embedding_model": connection.model,
        }
        if not connection.api_key:
            metrics["configuration_error"] = "chapter_embedding_api_key_missing"
            metrics["embedding_failure_count"] = len(photos)
            metrics["degraded_photo_count"] = len(photos)
            return {}, metrics

        features: dict[str, dict] = {}
        pending: list[tuple[Any, str, Any | None]] = []
        for photo in photos:
            content_hash = photo.content_sha256 or ""
            cached = None
            if content_hash:
                cached = await self.repo.get_cached(
                    photo.id,
                    content_sha256=content_hash,
                    feature_version=settings.chapter_feature_version,
                    embedding_provider=connection.provider,
                    embedding_model=connection.model,
                    embedding_dimension=settings.chapter_embedding_dimension,
                )
            if cached is not None and cached.status == "success" and cached.embedding:
                features[photo.id] = self._feature_payload(cached)
                metrics["cache_hit_count"] += 1
                metrics["embedding_success_count"] += 1
            else:
                pending.append((photo, content_hash, cached))

        batch_size = max(1, settings.chapter_embedding_batch_size)
        total_batches = (len(pending) + batch_size - 1) // batch_size
        for batch_index, offset in enumerate(range(0, len(pending), batch_size), 1):
            loaded: list[tuple[Any, str, Any, Any]] = []
            for photo, content_hash, cached in pending[offset : offset + batch_size]:
                try:
                    content = await self.storage.open_file(photo.storage_key)
                    actual_hash = content_hash or sha256(content).hexdigest()
                    image = await asyncio.to_thread(
                        encode_image_payload,
                        content,
                        filename=photo.filename,
                        max_edge=1024,
                        quality=82,
                    )
                    loaded.append((photo, actual_hash, cached, image))
                except Exception as exc:  # noqa: BLE001
                    metrics["embedding_failure_count"] += 1
                    stable_hash = content_hash or sha256(f"{photo.id}:{photo.storage_key}".encode()).hexdigest()
                    await self._persist_failure(photo, stable_hash, cached, connection, "image_unavailable", str(exc))
            if loaded:
                embeddings, embedding_error = await self._embed([item[3] for item in loaded], connection)
                for index, (photo, content_hash, cached, _) in enumerate(loaded):
                    embedding = embeddings[index] if embeddings is not None else None
                    record = await self.repo.upsert(cached, {
                        "photo_id": photo.id,
                        "content_sha256": content_hash,
                        "feature_version": settings.chapter_feature_version,
                        "embedding_provider": connection.provider,
                        "embedding_model": connection.model,
                        "embedding_dimension": settings.chapter_embedding_dimension,
                        "embedding": embedding,
                        "status": "success" if embedding is not None else "failed",
                        "error_code": "embedding_failed" if embedding_error else None,
                        "error_message": embedding_error[:1000] if embedding_error else None,
                    })
                    metrics["embedding_success_count" if embedding is not None else "embedding_failure_count"] += 1
                    features[photo.id] = self._feature_payload(record)
            if progress_callback is not None:
                await progress_callback(batch_index, total_batches)
        metrics["degraded_photo_count"] = sum(not item.get("embedding") for item in features.values())
        return features, metrics

    async def resolve_embedding_connection(self) -> ProviderConnectionConfig:
        settings = get_settings()
        connection = await self.default_configs.resolve("chapter_embedding")
        if connection is None:
            connection = ProviderConnectionConfig(
                provider=settings.chapter_embedding_provider,
                api_key=settings.chapter_embedding_api_key or settings.llm_api_key,
                api_url=settings.chapter_embedding_api_url,
                model=settings.chapter_embedding_model,
                source="env_fallback",
            )
        elif not connection.api_key:
            connection.api_key = settings.chapter_embedding_api_key or settings.llm_api_key
        return connection

    async def _embed(self, images, connection):  # noqa: ANN001
        settings = get_settings()
        try:
            response = await get_multimodal_embedding_provider(connection.provider).embed_images(
                ImageEmbeddingRequest(
                    images=images,
                    model=connection.model,
                    dimension=settings.chapter_embedding_dimension,
                    connection=connection,
                )
            )
            return response.embeddings, None
        except Exception as exc:  # noqa: BLE001
            return None, f"embedding: {exc}"

    async def _persist_failure(self, photo, content_hash, cached, connection, code, message):  # noqa: ANN001
        settings = get_settings()
        await self.repo.upsert(cached, {
            "photo_id": photo.id,
            "content_sha256": content_hash,
            "feature_version": settings.chapter_feature_version,
            "embedding_provider": connection.provider,
            "embedding_model": connection.model,
            "embedding_dimension": settings.chapter_embedding_dimension,
            "embedding": None,
            "status": "failed",
            "error_code": code,
            "error_message": message[:1000],
        })

    @staticmethod
    def _feature_payload(record) -> dict:  # noqa: ANN001
        return {
            "embedding": list(record.embedding or []),
            "embedding_provider": record.embedding_provider,
            "feature_status": record.status,
            "feature_version": record.feature_version,
            "embedding_model": record.embedding_model,
            "embedding_dimension": record.embedding_dimension,
        }
