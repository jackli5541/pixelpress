from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.engines.cleaning_engine.face_analyzer import FaceFeatureExtractor
from app.engines.cleaning_engine.local_analyzer import LocalPhotoAnalyzer
from app.engines.cleaning_engine.review_queue import ReviewQueueBuilder
from app.engines.cleaning_engine.service import CleaningDecisionPolicy, fallback_analysis
from app.repositories.album_repo import AlbumRepository
from app.repositories.cleaning_repo import CleaningRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.task_repo import TaskRepository
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.photo_selection import get_photo_review_status
from app.services.serializers import serialize_album, serialize_photo
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_service import TaskService
from app.storage.file_store import get_file_storage

PIPELINE_NAME = "cleaning"
TASK_TYPE = "clean_photos"
JOB_NAME = "run_cleaning_job"
USER_LOCKED_DECISION_SOURCES = {"user", "user_delegated"}


class CleaningRevisionConflictError(RuntimeError):
    def __init__(self, current_revision: int) -> None:
        super().__init__("cleaning content revision conflict")
        self.current_revision = current_revision


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
        self.decision_policy = CleaningDecisionPolicy()
        self.review_queue_builder = ReviewQueueBuilder()

    @staticmethod
    def _summary(photos: list[Any], *, duplicate_groups: int = 0) -> dict[str, int]:
        total = len(photos)
        removed = sum(photo.cleaning_decision == "remove" for photo in photos)
        return {
            "total": total,
            "retained": total - removed,
            "keep": sum(photo.cleaning_suggestion == "keep" for photo in photos),
            "review": sum(photo.cleaning_suggestion == "review" for photo in photos),
            "remove": sum(photo.cleaning_suggestion == "remove" for photo in photos),
            "excluded": removed,
            "pending_review": sum(get_photo_review_status(photo) == "pending_review" for photo in photos),
            "included": sum(get_photo_review_status(photo) == "included" for photo in photos),
            "kept": sum(get_photo_review_status(photo) == "kept" for photo in photos),
            "removed": removed,
            "duplicate_groups": duplicate_groups,
            "analysis_failures": sum("analysis_failed" in (photo.cleaning_issues or []) for photo in photos),
        }

    @staticmethod
    def _assert_revision(album, expected_revision: int | None) -> None:  # noqa: ANN001
        if expected_revision is not None and album.content_revision != expected_revision:
            raise CleaningRevisionConflictError(album.content_revision)

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

    @staticmethod
    def _is_hard_blur_rollout_enabled(album_id: str) -> bool:
        percent = get_settings().cleaning_hard_blur_rollout_percent
        bucket = int.from_bytes(sha256(f"hard-blur:{album_id}".encode("utf-8")).digest()[:2], "big") % 100
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
            "filename": photo.filename,
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
            features = dict(photo.cleaning_features)
            sharpness = features.get("sharpness") or {}
            hard_reject = bool(sharpness.get("hard_reject"))
            return {
                "photo_id": photo.id,
                "content_sha256": photo.content_sha256,
                "perceptual_hash": photo.perceptual_hash,
                "analysis_version": analyzer.version,
                "quality_score": float(photo.quality_score or 0),
                "suggestion": photo.cleaning_suggestion or "review",
                "confidence": float(photo.cleaning_confidence or 0),
                "issues": list(photo.cleaning_issues or []),
                "features": features,
                "clear_discard": hard_reject,
                "hard_reject": hard_reject,
                "hard_reject_reason": sharpness.get("hard_reject_reason"),
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
            face_analyzer = FaceFeatureExtractor(
                enabled=settings.cleaning_face_analysis_enabled,
                detector_model_path=settings.cleaning_face_detector_model_path,
                landmarker_model_path=settings.cleaning_face_landmarker_model_path,
                anime_model_path=settings.cleaning_anime_face_model_path,
                anime_enabled=settings.cleaning_anime_face_enabled,
                pose_enabled=settings.cleaning_pose_experiment_enabled,
                pose_model_path=settings.cleaning_pose_model_path,
            )
            analyzer = LocalPhotoAnalyzer(version, face_analyzer=face_analyzer)
            semaphore = asyncio.Semaphore(settings.cleaning_analysis_max_parallel)
            await self.runtime.heartbeat_step(task_id, "extracting_features", 15)
            analyses = await asyncio.gather(*(self._analyze_photo(photo, analyzer, semaphore) for photo in photos))

            await self.runtime.ensure_task_not_cancelled(task_id)
            await self.runtime.heartbeat_step(task_id, "grouping_duplicates", 65)
            rollout_enabled = self._is_rollout_enabled(album_id)
            auto_exclude_exact = rollout_enabled and settings.cleaning_auto_exclude_mode in {"exact_only", "exact_and_clear_quality"}
            auto_exclude_quality = (
                settings.cleaning_hard_blur_mode == "enforce"
                and self._is_hard_blur_rollout_enabled(album_id)
            )
            result = await asyncio.to_thread(
                self.decision_policy.apply,
                album_id,
                analyses,
                auto_exclude_exact=auto_exclude_exact,
                auto_exclude_quality=auto_exclude_quality,
            )

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
                if photo.cleaning_decision_source not in USER_LOCKED_DECISION_SOURCES:
                    next_decision = "remove" if item.get("auto_excluded") else None
                    next_source = item.get("auto_exclusion_source") if next_decision else None
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
                "hard_blur_mode": settings.cleaning_hard_blur_mode,
                "hard_blur_rollout_enabled": auto_exclude_quality,
                "hard_blur_shadow_matches": sum(bool(item.get("hard_reject")) for item in result["per_photo"]),
                "face_analysis_enabled": settings.cleaning_face_analysis_enabled,
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
        review_queue = self.review_queue_builder.build(photos, groups)
        return {
            "album_id": album_id,
            "analysis_version": next((photo.cleaning_analysis_version for photo in photos if photo.cleaning_analysis_version), None),
            "review_session_id": next((photo.cleaning_task_id for photo in photos if photo.cleaning_task_id), None),
            "content_revision": album.content_revision,
            "summary": self._summary(photos, duplicate_groups=len(groups)),
            "review_queue": review_queue,
            "groups": [self._serialize_group(group) for group in groups],
            "items": [serialize_photo(photo) for photo in photos],
        }

    async def apply_decisions(
        self,
        album_id: str,
        photo_ids: list[str],
        decision: str | None,
        *,
        source: str = "user",
        group_id: str | None = None,
        expected_content_revision: int | None = None,
    ) -> dict | None:
        album = await self.album_repo.get_album_for_update(album_id)
        if album is None:
            return None
        self._assert_revision(album, expected_content_revision)
        if decision not in {None, "keep", "remove"}:
            raise ValueError("invalid cleaning decision")
        photos = {photo.id: photo for photo in await self.photo_repo.list_photos(album_id)}
        changed = 0
        changed_ids: list[str] = []
        missing: list[str] = []
        now = datetime.now(UTC)
        for photo_id in dict.fromkeys(photo_ids):
            photo = photos.get(photo_id)
            if photo is None:
                missing.append(photo_id)
                continue
            photo_changed = await self._set_decision(
                album_id,
                photo,
                decision,
                source=source,
                group_id=group_id,
                now=now,
                operation="batch" if len(photo_ids) > 1 else "single",
            )
            changed += int(photo_changed)
            if photo_changed:
                changed_ids.append(photo.id)
        if changed:
            album.content_revision += 1
            album.status = AlbumStatus.CLEANED
            await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)
        await self.session.commit()
        ordered_photos = list(photos.values())
        groups = await self.cleaning_repo.list_groups(album_id)
        summary = self._summary(ordered_photos, duplicate_groups=len(groups))
        remaining_review_count = len(self.review_queue_builder.build(ordered_photos, groups))
        return {
            "album_id": album_id,
            "changed": changed,
            "changed_items": [serialize_photo(photos[photo_id]) for photo_id in changed_ids],
            "missing_photo_ids": missing,
            "decision": decision,
            "summary": summary,
            "content_revision": album.content_revision,
            "remaining_review_count": remaining_review_count,
        }

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
        context: dict[str, Any] | None = None,
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
            "context_json": {"operation": operation, **(context or {})},
        })
        await self.photo_repo.update_photo(photo, {
            "cleaning_decision": decision,
            "cleaning_decision_source": source if decision is not None else None,
            "cleaning_decided_at": now if decision is not None else None,
            "cleaning_recommendation": decision,
        })
        return True

    async def resolve_review_item(
        self,
        album_id: str,
        review_item_id: str,
        action: str,
        *,
        expected_content_revision: int | None = None,
    ) -> dict | None:
        album = await self.album_repo.get_album_for_update(album_id)
        if album is None:
            return None
        self._assert_revision(album, expected_content_revision)
        photos = {photo.id: photo for photo in await self.photo_repo.list_photos(album_id)}
        now = datetime.now(UTC)
        changed_ids: list[str] = []
        resolved_action = action

        if review_item_id.startswith("photo:"):
            photo_id = review_item_id.removeprefix("photo:")
            photo = photos.get(photo_id)
            if photo is None or action not in {"keep", "remove"}:
                raise ValueError("invalid photo review item or action")
            source = "user"
            decision = action
            if await self._set_decision(
                album_id,
                photo,
                decision,
                source=source,
                group_id=None,
                now=now,
                operation="resolve_review_photo",
                context={"requested_action": action, "policy_version": "cleaning-policy-v3"},
            ):
                changed_ids.append(photo.id)
            resolved_action = decision
        elif review_item_id.startswith("group:"):
            group_id = review_item_id.removeprefix("group:")
            group = await self.cleaning_repo.get_group(album_id, group_id)
            if group is None or action not in {"accept_preferred", "keep_all"}:
                raise ValueError("invalid group review item or action")
            source = "user"
            resolved_action = action
            for member in group.members:
                photo = photos.get(member.photo_id)
                if photo is None:
                    continue
                decision = "keep"
                if resolved_action == "accept_preferred" and member.photo_id != group.preferred_photo_id:
                    decision = "remove"
                if await self._set_decision(
                    album_id,
                    photo,
                    decision,
                    source=source,
                    group_id=group.id,
                    now=now,
                    operation="resolve_review_group",
                    context={
                        "requested_action": action,
                        "resolved_action": resolved_action,
                        "policy_version": "cleaning-policy-v3",
                    },
                ):
                    changed_ids.append(photo.id)
        else:
            raise ValueError("invalid review item")

        if changed_ids:
            album.content_revision += 1
            album.status = AlbumStatus.CLEANED
            await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)
        ordered_photos = list(photos.values())
        groups = await self.cleaning_repo.list_groups(album_id)
        summary = self._summary(ordered_photos, duplicate_groups=len(groups))
        remaining_review_count = len(self.review_queue_builder.build(ordered_photos, groups))
        changed_items = [serialize_photo(photos[photo_id]) for photo_id in changed_ids]
        await self.session.commit()
        return {
            "album_id": album_id,
            "review_item_id": review_item_id,
            "requested_action": action,
            "resolved_action": resolved_action,
            "changed": len(changed_ids),
            "changed_items": changed_items,
            "summary": summary,
            "content_revision": album.content_revision,
            "remaining_review_count": remaining_review_count,
        }

    async def resolve_remaining_reviews(
        self,
        album_id: str,
        *,
        expected_content_revision: int | None = None,
    ) -> dict | None:
        album = await self.album_repo.get_album_for_update(album_id)
        if album is None:
            return None
        self._assert_revision(album, expected_content_revision)
        ordered_photos = await self.photo_repo.list_photos(album_id)
        photos = {photo.id: photo for photo in ordered_photos}
        groups = await self.cleaning_repo.list_groups(album_id)
        groups_by_id = {group.id: group for group in groups}
        queue = self.review_queue_builder.build(ordered_photos, groups)
        now = datetime.now(UTC)
        changed_ids: list[str] = []

        for item in queue:
            if item["kind"] == "single_photo":
                photo = photos.get(item["photo_ids"][0])
                if photo is None or photo.cleaning_decision is not None:
                    continue
                decision = "remove" if photo.cleaning_suggestion == "remove" else "keep"
                if await self._set_decision(
                    album_id,
                    photo,
                    decision,
                    source="user_delegated",
                    group_id=None,
                    now=now,
                    operation="resolve_remaining_review_photo",
                    context={"policy_version": "cleaning-policy-v3"},
                ):
                    changed_ids.append(photo.id)
                continue

            group = groups_by_id.get(item.get("group_id"))
            if group is None:
                continue
            resolved_action = "accept_preferred" if float(group.confidence or 0) >= 0.8 else "keep_all"
            for photo_id in item["photo_ids"]:
                photo = photos.get(photo_id)
                if photo is None or photo.cleaning_decision is not None:
                    continue
                decision = "keep"
                if resolved_action == "accept_preferred" and photo.id != group.preferred_photo_id:
                    decision = "remove"
                if await self._set_decision(
                    album_id,
                    photo,
                    decision,
                    source="user_delegated",
                    group_id=group.id,
                    now=now,
                    operation="resolve_remaining_review_group",
                    context={
                        "resolved_action": resolved_action,
                        "policy_version": "cleaning-policy-v3",
                    },
                ):
                    changed_ids.append(photo.id)

        if changed_ids:
            album.content_revision += 1
            album.status = AlbumStatus.CLEANED
            await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)
        summary = self._summary(ordered_photos, duplicate_groups=len(groups))
        remaining_review_count = len(self.review_queue_builder.build(ordered_photos, groups))
        changed_items = [serialize_photo(photos[photo_id]) for photo_id in dict.fromkeys(changed_ids)]
        await self.session.commit()
        return {
            "album_id": album_id,
            "resolved_review_count": len(queue),
            "changed": len(changed_items),
            "changed_items": changed_items,
            "summary": summary,
            "content_revision": album.content_revision,
            "remaining_review_count": remaining_review_count,
        }

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
            if clear_user_decisions or photo.cleaning_decision_source not in USER_LOCKED_DECISION_SOURCES:
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
