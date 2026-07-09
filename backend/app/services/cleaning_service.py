from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.engines.cleaning_engine.service import run_cleaning
from app.repositories.album_repo import AlbumRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.task_repo import TaskRepository
from app.services.serializers import serialize_album
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_service import TaskService

PIPELINE_NAME = "cleaning"
PIPELINE_VERSION = "p0-async-v1"
TASK_TYPE = "clean_photos"
JOB_NAME = "run_cleaning_job"


class CleaningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.task_repo = TaskRepository(session)
        self.task_service = TaskService(session)
        self.runtime = TaskRuntimeService(self.task_service)

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

    async def request_cleaning(self, album_id: str, user_id: str | None) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=TASK_TYPE,
            task_params=None,
            idempotency_key=f"clean:{album_id}:{album.content_revision}",
            requested_revision=album.content_revision,
            resource_type="album",
            resource_id=album_id,
            job_name=JOB_NAME,
            pipeline_name=PIPELINE_NAME,
            pipeline_version=PIPELINE_VERSION,
            max_attempts=get_settings().queue_max_attempts,
        )

    async def execute_cleaning(self, task_id: str, album_id: str) -> dict | None:
        started = perf_counter()
        settings = get_settings()
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.content_revision)
            await self.runtime.heartbeat_step(task_id, "loading_photos", 5)
            photos = await self.photo_repo.list_photos(album_id)
            if not photos:
                album.status = AlbumStatus.CLEANED
                album.content_revision += 1
                await self._update_task_debug(task_id, debug_payload={"mode": settings.ai_mode_b1, "fallback_used": True, "stage": "loading_photos", "reason": "no_photos"})
                await self.task_service.complete_success(
                    task_id,
                    result_payload={"summary": {"total": 0, "keep": 0, "remove": 0}},
                    metrics_payload={"duration_ms": round((perf_counter() - started) * 1000), "photo_count": 0},
                    result_revision=album.content_revision,
                )
                await self.session.commit()
                return {"summary": {"total": 0, "keep": 0, "remove": 0}}

            await self.runtime.ensure_task_not_cancelled(task_id)
            await self.runtime.heartbeat_step(task_id, "scoring_photos", 25)
            result = run_cleaning(
                album_id,
                [
                    {
                        "id": photo.id,
                        "filename": photo.filename,
                        "url": photo.url,
                        "size": photo.size,
                        "width": photo.width,
                        "height": photo.height,
                        "content_type": photo.content_type,
                    }
                    for photo in photos
                ],
            )
            await self._update_task_debug(
                task_id,
                result_payload={"summary": result["summary"]},
                debug_payload={"mode": settings.ai_mode_b1, "fallback_used": True, "stage": "scoring_photos", "reason": "rule_engine_only"},
            )

            await self.runtime.ensure_task_not_cancelled(task_id)
            await self.runtime.heartbeat_step(task_id, "persisting_results", 75)
            for item in result["per_photo"]:
                photo = await self.photo_repo.get_photo(album_id, item["photo_id"])
                if photo is None:
                    continue
                await self.photo_repo.update_photo(
                    photo,
                    {
                        "quality_score": item["quality_score"],
                        "scene_tags": item["tags"],
                        "cleaning_recommendation": item["recommendation"],
                        "cleaning_issues": item["issues"],
                    },
                )

            album.status = AlbumStatus.CLEANED
            album.content_revision += 1
            await self.task_service.complete_success(
                task_id,
                result_payload={"summary": result["summary"]},
                metrics_payload={
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "photo_count": len(photos),
                    "fallback_used": True,
                },
                result_revision=album.content_revision,
            )
            await self.session.commit()
            return {"summary": result["summary"]}
        except RuntimeError as exc:
            code = "task_cancelled" if "cancelled" in str(exc) else "stale_task"
            await self.task_service.complete_failure(
                task_id,
                error_code=code,
                error_message=str(exc),
                retryable=False,
                debug_payload={"stage": "persisting_results", "reason": str(exc)},
            )
            await self.session.commit()
            return None
        except Exception as exc:  # noqa: BLE001
            await self.task_service.complete_failure(
                task_id,
                error_code="cleaning_failed",
                error_message=str(exc)[:500],
                retryable=False,
                debug_payload={
                    "stage": "persisting_results",
                    "reason": str(exc)[:255],
                    "exception_type": exc.__class__.__name__,
                },
            )
            await self.session.commit()
            return None

    async def start_cleaning(self, album_id: str):
        return await self.request_cleaning(album_id, None)

    async def reset_cleaning(self, album_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None

        photos = await self.photo_repo.list_photos(album_id)
        for photo in photos:
            await self.photo_repo.update_photo(
                photo,
                {
                    "quality_score": None,
                    "scene_tags": None,
                    "cleaning_recommendation": None,
                    "cleaning_issues": None,
                },
            )

        album.status = AlbumStatus.UPLOADED
        album.content_revision += 1
        await self.session.commit()
        return serialize_album(album)
