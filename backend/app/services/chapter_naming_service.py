from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ImagePayload
from app.core.config import get_settings
from app.engines.chapter_engine.image_payloads import encode_image_payload
from app.engines.chapter_engine.prompt_pipeline import name_chapter_with_ai
from app.services.project_ai_config_service import ProjectAIConfigService
from app.storage.file_store import get_file_storage


class ChapterNamingService:
    def __init__(self, session: AsyncSession) -> None:
        self.ai_config_service = ProjectAIConfigService(session)
        self.storage = get_file_storage()

    async def _representative_images(
        self,
        chapter: dict[str, Any],
        photo_by_id: dict[str, Any],
    ) -> tuple[list[ImagePayload], list[str]]:
        settings = get_settings()
        representative_ids = list(
            (chapter.get("clustering_explanation") or {}).get("representative_photo_ids") or []
        )[: settings.chapter_representative_photo_count]
        images: list[ImagePayload] = []
        loaded_ids: list[str] = []
        for photo_id in representative_ids:
            photo = photo_by_id.get(photo_id)
            if photo is None:
                continue
            try:
                content = await self.storage.open_file(photo.storage_key)
                images.append(
                    encode_image_payload(
                        content,
                        filename=photo.filename,
                        max_edge=settings.ai_image_max_edge,
                    )
                )
                loaded_ids.append(photo_id)
            except Exception:  # noqa: BLE001
                continue
        return images, loaded_ids

    async def name_chapters(
        self,
        album_id: str,
        chapters: list[dict[str, Any]],
        photo_payloads: list[dict[str, Any]],
        photo_by_id: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        settings = get_settings()
        connection = await self.ai_config_service.resolve_for_album(
            album_id,
            stage="chapter",
            model_hint=settings.ai_model_b2,
            provider_hint=settings.ai_provider_b2,
        )
        payload_by_id = {str(photo["id"]): photo for photo in photo_payloads}
        semaphore = asyncio.Semaphore(settings.chapter_naming_max_parallel)

        async def name_one(chapter: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            async with semaphore:
                members = [
                    payload_by_id[photo_id]
                    for photo_id in chapter.get("photo_ids", [])
                    if photo_id in payload_by_id
                ]
                images, loaded_ids = await self._representative_images(chapter, photo_by_id)
                if not images:
                    return chapter, {"named": False, "reason": "representative_images_unavailable"}
                naming_chapter = dict(chapter)
                explanation = dict(naming_chapter.get("clustering_explanation") or {})
                explanation["representative_photo_ids"] = loaded_ids
                naming_chapter["clustering_explanation"] = explanation
                try:
                    output, debug = await name_chapter_with_ai(
                        naming_chapter,
                        members,
                        images=images,
                        provider_connection=connection,
                    )
                except Exception as exc:  # noqa: BLE001
                    return chapter, {
                        "named": False,
                        "reason": "chapter_naming_failed",
                        "exception_type": exc.__class__.__name__,
                        "error": str(exc)[:255],
                    }
                updated = dict(chapter)
                updated["name"] = output.name.strip()
                updated["description"] = output.description.strip()
                explanation = dict(updated.get("clustering_explanation") or {})
                explanation["naming_source"] = "multimodal_llm"
                updated["clustering_explanation"] = explanation
                return updated, {
                    "named": True,
                    "provider": debug.get("provider"),
                    "model": debug.get("model"),
                }

        results = await asyncio.gather(*(name_one(chapter) for chapter in chapters))
        outcomes = [outcome for _, outcome in results]
        return [chapter for chapter, _ in results], {
            "named_count": sum(bool(outcome.get("named")) for outcome in outcomes),
            "fallback_count": sum(not bool(outcome.get("named")) for outcome in outcomes),
            "provider": next((outcome.get("provider") for outcome in outcomes if outcome.get("provider")), None),
            "model": next((outcome.get("model") for outcome in outcomes if outcome.get("model")), None),
            "outcomes": outcomes,
            "source": connection.source,
            "project_id": connection.project_id,
            "config_id": connection.config_id,
        }
