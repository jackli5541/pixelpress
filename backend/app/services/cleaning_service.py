from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.engines.cleaning_engine.local_analyzer import LocalPhotoAnalyzer
from app.engines.cleaning_engine.service import build_cleaning_result, fallback_analysis
from app.repositories.album_repo import AlbumRepository
from app.repositories.cleaning_repo import CleaningRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.task_repo import TaskRepository
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_album, serialize_photo
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_service import TaskService
from app.storage.file_store import get_file_storage

PIPELINE_NAME = "cleaning"
TASK_TYPE = "clean_photos"
JOB_NAME = "run_cleaning_job"


class CleaningService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.cleaning_repo = CleaningRepository(session)
        self.task_repo = TaskRepository(session)
        self.task_service = TaskService(session)
        self.runtime = TaskRuntimeService(self.task_service)
        self.storage = get_file_storage()
        self.render_artifacts = RenderArtifactService()

    async def _update_task_debug(self, task_id: str, *, result_payload: dict | None = None, debug_payload: dict | None = None):
        task = await self.task_repo.get_task(task_id)
        if task is None:
            return
        updates: dict[str, Any] = {}
        if result_payload is not None:
            updates["result_payload"] = result_payload
        if debug_payload is not None:
            updates["debug_payload"] = {**(task.debug_payload or {}), **debug_payload}
        if updates:
            await self.task_repo.update_task(task, updates)

    @staticmethod
    def _is_rollout_enabled(album_id: str) -> bool:
        percent = get_settings().cleaning_rollout_percent
        bucket = int.from_bytes(sha256(album_id.encode("utf-8")).digest()[:2], "big") % 100
        return bucket < percent

    async def request_cleaning(self, album_id: str, user_id: str | None) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        version = get_settings().cleaning_pipeline_version
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=TASK_TYPE,
            task_params={"pipeline_version": version},
            idempotency_key=f"clean:{album_id}:{album.content_revision}:{version}",
            requested_revision=album.content_revision,
            resource_type="album",
            resource_id=album_id,
            job_name=JOB_NAME,
            pipeline_name=PIPELINE_NAME,
            pipeline_version=version,
            max_attempts=get_settings().queue_max_attempts,
        )

    async def _analyze_photo(self, photo, analyzer: LocalPhotoAnalyzer, semaphore: asyncio.Semaphore) -> dict[str, Any]:  # noqa: ANN001
        base = {
            "id": photo.id,
            "width": photo.width,
            "height": photo.height,
            "size": photo.size,
            "content_type": photo.content_type,
            "taken_at": photo.taken_at,
            "device_model": photo.device_model,
            "uploaded_at": photo.uploaded_at,
        }
        if (
            photo.cleaning_analysis_version == analyzer.version
            and photo.cleaning_features
            and photo.content_sha256
            and photo.perceptual_hash
        ):
            return {
                "photo_id": photo.id,
                "content_sha256": photo.content_sha256,
                "perceptual_hash": photo.perceptual_hash,
                "analysis_version": analyzer.version,
                "quality_score": float(photo.quality_score or 0),
                "suggestion": photo.cleaning_suggestion or "review",
                "confidence": float(photo.cleaning_confidence or 0),
                "issues": list(photo.cleaning_issues or []),
                "features": dict(photo.cleaning_features),
                "taken_at": photo.taken_at,
                "device_model": photo.device_model,
                "uploaded_at": photo.uploaded_at,
                "cache_hit": True,
            }
        async with semaphore:
            try:
                content = await self.storage.open_file(photo.storage_key)
                result = await asyncio.to_thread(analyzer.analyze, content, base)
            except Exception as exc:  # noqa: BLE001
                result = fallback_analysis(base, analyzer.version)
                result["features"]["fallback_reason"] = exc.__class__.__name__
        result.update({"taken_at": photo.taken_at, "device_model": photo.device_model, "uploaded_at": photo.uploaded_at})
        return result

    async def execute_cleaning(self, task_id: str, album_id: str, *, pipeline_version: str | None = None) -> dict | None:
        started = perf_counter()
        settings = get_settings()
        version = pipeline_version or settings.cleaning_pipeline_version
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.content_revision)
            await self.runtime.heartbeat_step(task_id, "loading_photos", 5)
            photos = await self.photo_repo.list_photos(album_id)
            analyzer = LocalPhotoAnalyzer(version)
            semaphore = asyncio.Semaphore(settings.cleaning_analysis_max_parallel)
            await self.runtime.heartbeat_step(task_id, "extracting_features", 15)
            analyses = await asyncio.gather(*(self._analyze_photo(photo, analyzer, semaphore) for photo in photos))

            await self.runtime.ensure_task_not_cancelled(task_id)
            await self.runtime.heartbeat_step(task_id, "grouping_duplicates", 65)
            rollout_enabled = self._is_rollout_enabled(album_id)
            auto_exclude = rollout_enabled and settings.cleaning_auto_exclude_mode == "exact_only"
            result = await asyncio.to_thread(build_cleaning_result, album_id, analyses, auto_exclude_exact=auto_exclude)

            await self.runtime.ensure_task_not_cancelled(task_id)
            await self.runtime.heartbeat_step(task_id, "persisting_results", 80)
            effective_changed = False
            photos_by_id = {photo.id: photo for photo in photos}
            for item in result["per_photo"]:
                photo = photos_by_id[item["photo_id"]]
                updates: dict[str, Any] = {
                    "content_sha256": item.get("content_sha256"),
                    "perceptual_hash": item.get("perceptual_hash"),
                    "cleaning_analysis_version": version,
                    "cleaning_task_id": task_id,
                    "cleaning_features": item["features"],
                    "quality_score": item["quality_score"],
                    "cleaning_suggestion": item["suggestion"],
                    "cleaning_confidence": item["confidence"],
                    "cleaning_issues": item["issues"],
                }
                if photo.cleaning_decision_source != "user":
                    next_decision = "remove" if item.get("auto_excluded") else None
                    next_source = "system_exact_duplicate" if next_decision else None
                    if photo.cleaning_decision != next_decision:
                        effective_changed = True
                        await self.cleaning_repo.add_decision_event({
                            "album_id": album_id,
                            "photo_id": photo.id,
                            "task_id": task_id,
                            "previous_decision": photo.cleaning_decision,
                            "decision": next_decision,
                            "source": next_source or "system_recalculation",
                            "context_json": {"analysis_version": version},
                        })
                    updates.update({
                        "cleaning_decision": next_decision,
                        "cleaning_decision_source": next_source,
                        "cleaning_decided_at": datetime.now(UTC) if next_decision else None,
                        "cleaning_recommendation": next_decision,
                    })
                await self.photo_repo.update_photo(photo, updates)

            await self.cleaning_repo.replace_groups(album_id, task_id, version, result["groups"])
            album.status = AlbumStatus.CLEANED
            album.content_revision += 1
            await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)
            metrics = {
                "duration_ms": round((perf_counter() - started) * 1000),
                "photo_count": len(photos),
                "cache_hits": sum(bool(item.get("cache_hit")) for item in analyses),
                "analysis_failures": result["summary"]["analysis_failures"],
                "rollout_enabled": rollout_enabled,
                "auto_exclude_mode": settings.cleaning_auto_exclude_mode,
                "effective_selection_changed": effective_changed,
            }
            await self._update_task_debug(
                task_id,
                result_payload={"summary": result["summary"]},
                debug_payload={"mode": "local", "fallback_used": bool(result["summary"]["analysis_failures"]), "analysis_version": version},
            )
            await self.task_service.complete_success(
                task_id,
                result_payload={"summary": result["summary"]},
                metrics_payload=metrics,
                result_revision=album.content_revision,
            )
            await self.session.commit()
            return {"summary": result["summary"]}
        except RuntimeError as exc:
            code = "task_cancelled" if "cancelled" in str(exc) else "stale_task"
            await self.task_service.complete_failure(task_id, error_code=code, error_message=str(exc), retryable=False)
            await self.session.commit()
            return None
        except Exception as exc:  # noqa: BLE001
            await self.session.rollback()
            await self.task_service.complete_failure(
                task_id,
                error_code="cleaning_failed",
                error_message=str(exc)[:500],
                retryable=True,
                debug_payload={"stage": "cleaning", "reason": str(exc)[:255], "exception_type": exc.__class__.__name__},
            )
            await self.session.commit()
            return None

    @staticmethod
    def _serialize_group(group) -> dict[str, Any]:  # noqa: ANN001
        members = sorted(group.members, key=lambda item: (item.rank, item.id))
        return {
            "id": group.id,
            "group_type": group.group_type,
            "confidence": group.confidence,
            "analysis_version": group.analysis_version,
            "preferred_photo_id": group.preferred_photo_id,
            "thresholds": group.thresholds_json,
            "explanation": group.explanation_json,
            "members": [
                {
                    "photo_id": member.photo_id,
                    "relation_type": member.relation_type,
                    "hamming_distance": member.hamming_distance,
                    "burst_time_delta_ms": member.burst_time_delta_ms,
                    "preferred_score": member.preferred_score,
                    "rank": member.rank,
                    "is_preferred": member.is_preferred,
                    "auto_excluded": member.auto_excluded,
                    "factors": member.factors_json,
                }
                for member in members
            ],
        }

    async def get_results(self, album_id: str) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        photos = await self.photo_repo.list_photos(album_id)
        groups = await self.cleaning_repo.list_groups(album_id)
        return {
            "album_id": album_id,
            "analysis_version": next((photo.cleaning_analysis_version for photo in photos if photo.cleaning_analysis_version), None),
            "summary": {
                "total": len(photos),
                "keep": sum(photo.cleaning_suggestion == "keep" for photo in photos),
                "review": sum(photo.cleaning_suggestion == "review" for photo in photos),
                "remove": sum(photo.cleaning_suggestion == "remove" for photo in photos),
                "excluded": sum(photo.cleaning_decision == "remove" for photo in photos),
                "duplicate_groups": len(groups),
                "analysis_failures": sum("analysis_failed" in (photo.cleaning_issues or []) for photo in photos),
            },
            "groups": [self._serialize_group(group) for group in groups],
            "items": [serialize_photo(photo) for photo in photos],
        }

    async def apply_decisions(self, album_id: str, photo_ids: list[str], decision: str | None, *, source: str = "user", group_id: str | None = None) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        if decision not in {None, "keep", "remove"}:
            raise ValueError("invalid cleaning decision")
        photos = {photo.id: photo for photo in await self.photo_repo.list_photos(album_id)}
        changed = 0
        missing: list[str] = []
        now = datetime.now(UTC)
        for photo_id in dict.fromkeys(photo_ids):
            photo = photos.get(photo_id)
            if photo is None:
                missing.append(photo_id)
                continue
            changed += int(await self._set_decision(
                album_id,
                photo,
                decision,
                source=source,
                group_id=group_id,
                now=now,
                operation="batch" if len(photo_ids) > 1 else "single",
            ))
        if changed:
            album.content_revision += 1
            album.status = AlbumStatus.CLEANED
            await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)
        await self.session.commit()
        return {"album_id": album_id, "changed": changed, "missing_photo_ids": missing, "decision": decision}

    async def _set_decision(
        self,
        album_id: str,
        photo,
        decision: str | None,
        *,
        source: str,
        group_id: str | None,
        now: datetime,
        operation: str,
    ) -> bool:  # noqa: ANN001
        if photo.cleaning_decision == decision and photo.cleaning_decision_source == (source if decision is not None else None):
            return False
        await self.cleaning_repo.add_decision_event({
            "album_id": album_id,
            "photo_id": photo.id,
            "task_id": photo.cleaning_task_id,
            "group_id": group_id,
            "previous_decision": photo.cleaning_decision,
            "decision": decision,
            "source": source,
            "context_json": {"operation": operation},
        })
        await self.photo_repo.update_photo(photo, {
            "cleaning_decision": decision,
            "cleaning_decision_source": source if decision is not None else None,
            "cleaning_decided_at": now if decision is not None else None,
            "cleaning_recommendation": decision,
        })
        return True

    async def accept_group_preferred(self, album_id: str, group_id: str) -> dict | None:
        group = await self.cleaning_repo.get_group(album_id, group_id)
        if group is None or group.preferred_photo_id is None:
            return None
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        photos = {photo.id: photo for photo in await self.photo_repo.list_photos(album_id)}
        now = datetime.now(UTC)
        kept = 0
        removed = 0
        for member in group.members:
            photo = photos.get(member.photo_id)
            if photo is None:
                continue
            decision = "keep" if member.photo_id == group.preferred_photo_id else "remove"
            changed = await self._set_decision(
                album_id,
                photo,
                decision,
                source="user",
                group_id=group_id,
                now=now,
                operation="accept_group_preferred",
            )
            if changed and decision == "keep":
                kept += 1
            elif changed:
                removed += 1
        if kept or removed:
            album.content_revision += 1
            album.status = AlbumStatus.CLEANED
            await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)
        await self.session.commit()
        return {
            "group_id": group_id,
            "preferred_photo_id": group.preferred_photo_id,
            "kept": kept,
            "removed": removed,
        }

    async def reset_cleaning(self, album_id: str, *, clear_user_decisions: bool = False):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        photos = await self.photo_repo.list_photos(album_id)
        for photo in photos:
            updates: dict[str, Any] = {
                "content_sha256": None,
                "perceptual_hash": None,
                "cleaning_analysis_version": None,
                "cleaning_task_id": None,
                "cleaning_features": None,
                "quality_score": None,
                "cleaning_suggestion": None,
                "cleaning_confidence": None,
                "cleaning_issues": None,
            }
            if clear_user_decisions or photo.cleaning_decision_source != "user":
                updates.update({"cleaning_decision": None, "cleaning_decision_source": None, "cleaning_decided_at": None, "cleaning_recommendation": None})
            await self.photo_repo.update_photo(photo, updates)
        await self.cleaning_repo.clear_groups(album_id)
        album.status = AlbumStatus.UPLOADED
        album.content_revision += 1
        await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.UPLOADED)
        await self.session.flush()
        await self.session.refresh(album)
        result = serialize_album(album)
        await self.session.commit()
        return result

    async def start_cleaning(self, album_id: str):
        return await self.request_cleaning(album_id, None)
