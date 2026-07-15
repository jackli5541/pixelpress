from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.engines.chapter_engine.prompt_pipeline import cluster_photos_with_ai
from app.engines.chapter_engine.service import cluster_photos
from app.repositories.album_repo import AlbumRepository
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.task_repo import TaskRepository
from app.services.project_ai_config_service import ProjectAIConfigService
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_chapter
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_service import TaskService

PIPELINE_NAME = "chaptering"
PIPELINE_VERSION = "p0-async-v1"
TASK_TYPE = "cluster_chapters"
JOB_NAME = "run_cluster_chapters_job"


class ChapterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.chapter_repo = ChapterRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.task_repo = TaskRepository(session)
        self.ai_config_service = ProjectAIConfigService(session)
        self.task_service = TaskService(session)
        self.runtime = TaskRuntimeService(self.task_service)
        self.render_artifacts = RenderArtifactService()

    async def _clear_render_artifacts(self, album) -> None:
        await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)


    async def _update_task_debug(self, task_id: str, *, provider: str | None = None, model: str | None = None, result_payload: dict | None = None, debug_payload: dict | None = None):
        task = await self.task_repo.get_task(task_id)
        if task is None:
            return
        updates = {}
        if provider is not None:
            updates["provider"] = provider
        if model is not None:
            updates["model"] = model
        if result_payload is not None:
            updates["result_payload"] = result_payload
        if debug_payload is not None:
            merged_debug: dict[str, Any] = dict(task.debug_payload or {})
            for key, value in debug_payload.items():
                if isinstance(value, dict) and isinstance(merged_debug.get(key), dict):
                    merged_debug[key] = {**merged_debug[key], **value}
                else:
                    merged_debug[key] = value
            updates["debug_payload"] = merged_debug
        if updates:
            await self.task_repo.update_task(task, updates)

    async def list_chapters(self, album_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        chapters = await self.chapter_repo.list_chapters(album_id)
        return [serialize_chapter(chapter) for chapter in chapters]

    async def create_chapter(self, album_id: str, payload: dict):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        existing = await self.chapter_repo.list_chapters(album_id)
        chapter = await self.chapter_repo.create_chapter(
            {
                "album_id": album_id,
                "name": payload.get("name", "新章节"),
                "description": payload.get("description", ""),
                "order_index": len(existing),
            },
            payload.get("photo_ids", []),
        )
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        return serialize_chapter(chapter)

    async def update_chapter(self, album_id: str, chapter_id: str, payload: dict):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None, "album"
        chapter = await self.chapter_repo.get_chapter(album_id, chapter_id)
        if chapter is None:
            return None, "chapter"
        photo_ids = payload.pop("photo_ids", None)
        updated = await self.chapter_repo.update_chapter(chapter, payload, photo_ids)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        return serialize_chapter(updated), None

    async def delete_chapter(self, album_id: str, chapter_id: str) -> str | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return "album"
        chapter = await self.chapter_repo.get_chapter(album_id, chapter_id)
        if chapter is None:
            return "chapter"
        await self.chapter_repo.delete_chapter(chapter)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        return None

    async def move_photos(self, album_id: str, photo_ids: list[str], target_chapter_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None, "album"
        chapters = await self.chapter_repo.list_chapters(album_id)
        target = next((chapter for chapter in chapters if chapter.id == target_chapter_id), None)
        if target is None:
            return None, "target"
        for chapter in chapters:
            current_ids = [link.photo_id for link in sorted(chapter.photo_links, key=lambda item: item.order_index)]
            if chapter.id == target_chapter_id:
                existing = set(current_ids)
                for photo_id in photo_ids:
                    if photo_id not in existing:
                        current_ids.append(photo_id)
                        existing.add(photo_id)
            else:
                current_ids = [pid for pid in current_ids if pid not in photo_ids]
            await self.chapter_repo.update_chapter(chapter, {}, current_ids)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        refreshed = await self.chapter_repo.get_chapter(album_id, target_chapter_id)
        return {"target_chapter": serialize_chapter(refreshed), "moved_count": len(photo_ids)}, None

    async def merge_chapters(self, album_id: str, source_ids: list[str], target_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None, "album"
        chapters = await self.chapter_repo.list_chapters(album_id)
        target = next((chapter for chapter in chapters if chapter.id == target_id), None)
        if target is None:
            return None, "target"
        target_ids = [link.photo_id for link in sorted(target.photo_links, key=lambda item: item.order_index)]
        merged_count = 0
        for chapter in chapters:
            if chapter.id not in source_ids or chapter.id == target_id:
                continue
            for link in sorted(chapter.photo_links, key=lambda item: item.order_index):
                if link.photo_id not in target_ids:
                    target_ids.append(link.photo_id)
                    merged_count += 1
            await self.chapter_repo.delete_chapter(chapter)
        await self.chapter_repo.update_chapter(target, {}, target_ids)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        refreshed = await self.chapter_repo.get_chapter(album_id, target_id)
        return {"chapter": serialize_chapter(refreshed), "merged_photos": merged_count}, None

    async def request_cluster_chapters(self, album_id: str, user_id: str | None) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=TASK_TYPE,
            task_params=None,
            idempotency_key=f"cluster:{album_id}:{album.content_revision}",
            requested_revision=album.content_revision,
            resource_type="album",
            resource_id=album_id,
            job_name=JOB_NAME,
            pipeline_name=PIPELINE_NAME,
            pipeline_version=PIPELINE_VERSION,
            max_attempts=get_settings().queue_max_attempts,
        )

    async def execute_cluster_chapters(self, task_id: str, album_id: str):
        started = perf_counter()
        settings = get_settings()
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.content_revision)
            await self.runtime.heartbeat_step(task_id, "loading_photos", 10)
            photos = await self.photo_repo.list_photos(album_id)
            keep_photos = [photo for photo in photos if photo.cleaning_recommendation != "remove"]
            if not keep_photos:
                album.status = AlbumStatus.CLUSTERED
                album.content_revision += 1
                await self.task_service.complete_success(
                    task_id,
                    result_payload={"chapter_count": 0},
                    metrics_payload={"duration_ms": round((perf_counter() - started) * 1000), "photo_count": 0, "chapter_count": 0},
                    result_revision=album.content_revision,
                )
                await self.session.commit()
                return {"chapters": []}

            photo_payloads = [{
                "id": photo.id,
                "filename": photo.filename,
                "uploaded_at": photo.uploaded_at.isoformat() if photo.uploaded_at else None,
                "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
                "gps_latitude": photo.gps_latitude,
                "gps_longitude": photo.gps_longitude,
                "device_model": photo.device_model,
                "scene_tags": photo.scene_tags,
                "quality_score": photo.quality_score,
            } for photo in keep_photos]
            baseline_chapters = cluster_photos(photo_payloads, strategy="time_based")

            chapter_list: list[dict]
            debug_payload: dict[str, Any] = {"mode": settings.ai_mode_b2, "fallback_used": False, "stage": "loading_photos", "reason": "pending"}
            if settings.ai_enabled and settings.ai_mode_b2 != "rule":
                try:
                    provider_connection = await self.ai_config_service.resolve_for_album(
                        album_id,
                        stage="chapter",
                        model_hint=settings.ai_model_b2,
                        provider_hint=settings.ai_provider_b2,
                    )
                    ai_result, provider_debug = await cluster_photos_with_ai(
                        photo_payloads,
                        baseline=baseline_chapters,
                        provider_connection=provider_connection,
                    )
                    chapter_list = [chapter.model_dump() for chapter in ai_result.chapters]
                    debug_payload.update({
                        "stage": "calling_ai",
                        "reason": "ai_cluster_succeeded",
                        "provider_debug": provider_debug | {
                            "source": provider_connection.source,
                            "project_id": provider_connection.project_id,
                            "config_id": provider_connection.config_id,
                        },
                    })
                    await self._update_task_debug(
                        task_id,
                        provider=provider_debug.get("provider"),
                        model=provider_debug.get("model"),
                        result_payload={"chapter_count": len(chapter_list)},
                        debug_payload=debug_payload,
                    )
                except Exception as exc:  # noqa: BLE001
                    if settings.ai_fallback_on_error:
                        chapter_list = baseline_chapters
                        debug_payload.update({
                            "stage": "calling_ai",
                            "reason": "provider_failed_rule_fallback",
                            "fallback_used": True,
                            "exception_type": exc.__class__.__name__,
                            "error": str(exc)[:255],
                            "fallback": "rule",
                        })
                        await self._update_task_debug(task_id, debug_payload=debug_payload)
                    else:
                        await self.task_service.complete_failure(
                            task_id,
                            error_code="provider_failed",
                            error_message=str(exc)[:500],
                            retryable=False,
                            debug_payload={
                                "mode": settings.ai_mode_b2,
                                "stage": "calling_ai",
                                "reason": "provider_failed",
                                "exception_type": exc.__class__.__name__,
                                "error": str(exc)[:255],
                            },
                        )
                        await self.session.commit()
                        return None
            else:
                chapter_list = baseline_chapters
                debug_payload.update({"stage": "building_features", "reason": "rule_engine_only"})
                await self._update_task_debug(task_id, debug_payload=debug_payload)

            await self.runtime.ensure_task_not_cancelled(task_id)
            await self.runtime.heartbeat_step(task_id, "rebuilding_chapters", 70)
            await self.album_repo.clear_album_chapters(album_id)
            created = []
            for index, chapter_payload in enumerate(chapter_list):
                chapter = await self.chapter_repo.create_chapter(
                    {
                        "album_id": album_id,
                        "name": chapter_payload["name"],
                        "description": chapter_payload.get("description") or chapter_payload.get("time_range", ""),
                        "order_index": index,
                    },
                    chapter_payload.get("photo_ids", []),
                )
                created.append(serialize_chapter(chapter))

            album.status = AlbumStatus.CLUSTERED
            album.content_revision += 1
            await self.task_service.complete_success(
                task_id,
                result_payload={"chapter_count": len(created)},
                debug_payload=debug_payload,
                metrics_payload={
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "photo_count": len(keep_photos),
                    "chapter_count": len(created),
                    "fallback_used": debug_payload.get("fallback_used", False),
                },
                result_revision=album.content_revision,
            )
            await self.session.commit()
            return {"chapters": created}
        except RuntimeError as exc:
            code = "task_cancelled" if "cancelled" in str(exc) else "stale_task"
            await self.task_service.complete_failure(
                task_id,
                error_code=code,
                error_message=str(exc),
                retryable=False,
                debug_payload={"stage": "rebuilding_chapters", "reason": str(exc)},
            )
            await self.session.commit()
            return None
        except Exception as exc:  # noqa: BLE001
            await self.task_service.complete_failure(
                task_id,
                error_code="cluster_failed",
                error_message=str(exc)[:500],
                retryable=False,
                debug_payload={
                    "stage": "rebuilding_chapters",
                    "reason": str(exc)[:255],
                    "exception_type": exc.__class__.__name__,
                },
            )
            await self.session.commit()
            return None

    async def cluster_chapters(self, album_id: str):
        return await self.request_cluster_chapters(album_id, None)
