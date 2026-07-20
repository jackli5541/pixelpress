from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.engines.chapter_engine.sequential_clusterer import ALGORITHM_VERSION
from app.engines.chapter_engine.service import cluster_photos
from app.repositories.album_repo import AlbumRepository
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.task_repo import TaskRepository
from app.services.chapter_feature_service import ChapterFeatureService
from app.services.chapter_naming_service import ChapterNamingService
from app.services.photo_selection import is_photo_included, requires_photo_review
from app.services.serializers import serialize_chapter
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_service import TaskService
from app.services.theme_curation_service import ThemeCurationService


class ChapterClusteringTaskRunner:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.chapter_repo = ChapterRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.task_repo = TaskRepository(session)
        self.feature_service = ChapterFeatureService(session)
        self.naming_service = ChapterNamingService(session)
        self.task_service = TaskService(session)
        self.runtime = TaskRuntimeService(self.task_service)
        self.theme_service = ThemeCurationService(session)

    async def _update_task_debug(
        self,
        task_id: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        result_payload: dict | None = None,
        debug_payload: dict | None = None,
    ) -> None:
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

    async def execute(self, task_id: str, album_id: str):  # noqa: ANN201
        started = perf_counter()
        settings = get_settings()
        task = await self.task_repo.get_task(task_id)
        granularity = int((task.task_params or {}).get("granularity", 0)) if task else 0
        granularity = max(-2, min(2, granularity))
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.content_revision)
            await self.runtime.heartbeat_step(task_id, "loading_photos", 10)
            photos = await self.photo_repo.list_photos(album_id)
            pending_review_count = sum(requires_photo_review(photo) for photo in photos)
            if pending_review_count:
                await self.task_service.complete_failure(
                    task_id,
                    error_code="pending_photo_review",
                    error_message=f"{pending_review_count} photos require review",
                    retryable=False,
                )
                await self.session.commit()
                return None
            theme_context = await self.theme_service.confirmed_context(album_id, album.theme_input_revision)
            if theme_context is None:
                await self.task_service.complete_failure(
                    task_id,
                    error_code="theme_review_required",
                    error_message="theme review must be confirmed before clustering",
                    retryable=False,
                )
                await self.session.commit()
                return None
            excluded_ids = set(theme_context.get("excluded_photo_ids") or set())
            review_ids = set(theme_context.get("review_photo_ids") or set())
            if review_ids:
                await self.task_service.complete_failure(
                    task_id,
                    error_code="theme_review_incomplete",
                    error_message=f"{len(review_ids)} photos require theme review decisions",
                    retryable=False,
                )
                await self.session.commit()
                return None
            keep_photos = [
                photo for photo in photos
                if is_photo_included(photo) and photo.id not in excluded_ids and photo.id not in review_ids
            ]
            if not keep_photos:
                album.status = AlbumStatus.CLUSTERED
                album.content_revision += 1
                await self.task_service.complete_success(
                    task_id,
                    result_payload={"chapter_count": 0, "segment_count": 0},
                    metrics_payload={
                        "duration_ms": round((perf_counter() - started) * 1000),
                        "photo_count": 0,
                        "chapter_count": 0,
                        "segment_count": 0,
                    },
                    result_revision=album.content_revision,
                )
                await self.session.commit()
                return {"chapters": []}

            feature_metrics: dict[str, Any] = {
                "cache_hit_count": 0,
                "embedding_success_count": 0,
                "embedding_failure_count": len(keep_photos),
                "degraded_photo_count": len(keep_photos),
                "embedding_model": settings.chapter_embedding_model,
            }
            chapter_features: dict[str, dict] = {}
            feature_error: str | None = None
            if settings.ai_enabled:
                await self.runtime.heartbeat_step(task_id, "extracting_chapter_features", 20)
                try:
                    async def report_feature_progress(completed_batches: int, total_batches: int) -> None:
                        progress = 20 + min(14, round(14 * completed_batches / max(total_batches, 1)))
                        await self.runtime.heartbeat_step(task_id, "extracting_chapter_features", progress)

                    chapter_features, feature_metrics = await self.feature_service.extract(
                        album_id,
                        keep_photos,
                        progress_callback=report_feature_progress,
                    )
                except Exception as exc:  # noqa: BLE001
                    feature_error = str(exc)[:255]

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
                "perceptual_hash": photo.perceptual_hash,
                "cleaning_features": photo.cleaning_features,
                "chapter_features": chapter_features.get(photo.id),
            } for photo in keep_photos]
            await self.runtime.heartbeat_step(task_id, "clustering_events", 35)
            multimodal_available = int(feature_metrics.get("embedding_success_count") or 0) > 0
            clustering_mode = "embedding" if multimodal_available else "legacy"
            chapter_list = cluster_photos(
                photo_payloads,
                mode=clustering_mode,
                theme_context=theme_context,
                granularity=granularity,
            )
            algorithm_version = next(
                (item.get("clustering_algorithm_version") for item in chapter_list if item.get("clustering_algorithm_version")),
                ALGORITHM_VERSION,
            )
            feature_fallback = not multimodal_available
            debug_payload: dict[str, Any] = {
                "mode": settings.ai_mode_b2,
                "fallback_used": feature_fallback,
                "clustering_fallback_used": feature_fallback,
                "naming_fallback_used": False,
                "stage": "clustering_events",
                "reason": "embedding_unavailable_rule_fallback" if feature_fallback else "sequential_hierarchical_clustering",
                "theme": {
                    "profile_id": theme_context.get("profile_id"),
                    "title": theme_context.get("title"),
                    "chapter_strategy": theme_context.get("chapter_strategy"),
                    "constraints": theme_context.get("constraints", {}),
                    "excluded_photo_count": len(excluded_ids),
                    "review_photo_count": len(review_ids),
                    "relevance_coverage": theme_context.get("relevance_coverage", 0.0),
                },
                "clustering": {
                    "mode": clustering_mode,
                    "algorithm_version": algorithm_version,
                    "feature_error": feature_error,
                    **feature_metrics,
                },
            }
            if settings.ai_enabled and settings.ai_mode_b2 != "rule":
                try:
                    await self.runtime.heartbeat_step(task_id, "naming_chapters", 50)
                    chapter_list, naming_debug = await self.naming_service.name_chapters(
                        album_id,
                        chapter_list,
                        photo_payloads,
                        {photo.id: photo for photo in keep_photos},
                    )
                    debug_payload.update({
                        "stage": "naming_chapters",
                        "reason": "multimodal_naming_completed",
                        "fallback_used": feature_fallback,
                        "naming_fallback_used": naming_debug["fallback_count"] > 0,
                        "naming": naming_debug,
                    })
                    await self._update_task_debug(
                        task_id,
                        provider=naming_debug.get("provider"),
                        model=naming_debug.get("model"),
                        result_payload={"chapter_count": len(chapter_list)},
                        debug_payload=debug_payload,
                    )
                except Exception as exc:  # noqa: BLE001
                    debug_payload.update({
                        "stage": "naming_chapters",
                        "reason": "provider_failed_rule_fallback",
                        "fallback_used": feature_fallback,
                        "naming_fallback_used": True,
                        "exception_type": exc.__class__.__name__,
                        "error": str(exc)[:255],
                        "fallback": "rule",
                    })
                    await self._update_task_debug(task_id, debug_payload=debug_payload)
            else:
                debug_payload.update({"stage": "naming_chapters", "reason": "rule_naming_only"})
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
                        "clustering_source": chapter_payload.get("clustering_source", "algorithm"),
                        "clustering_algorithm_version": chapter_payload.get("clustering_algorithm_version"),
                        "clustering_quality": chapter_payload.get("clustering_quality"),
                        "clustering_needs_review": bool(chapter_payload.get("clustering_needs_review")),
                        "clustering_explanation": chapter_payload.get("clustering_explanation"),
                    },
                    chapter_payload.get("photo_ids", []),
                    chapter_payload.get("segments"),
                )
                created.append(serialize_chapter(chapter))

            album.status = AlbumStatus.CLUSTERED
            album.content_revision += 1
            await self.task_service.complete_success(
                task_id,
                result_payload={
                    "chapter_count": len(created),
                    "segment_count": sum(len(item.get("segments") or []) for item in chapter_list),
                    "clustering_algorithm_version": algorithm_version,
                },
                debug_payload=debug_payload,
                metrics_payload={
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "photo_count": len(keep_photos),
                    "chapter_count": len(created),
                    "segment_count": sum(len(item.get("segments") or []) for item in chapter_list),
                    "fallback_used": debug_payload.get("clustering_fallback_used", False),
                    "clustering_fallback_used": debug_payload.get("clustering_fallback_used", False),
                    "naming_fallback_used": debug_payload.get("naming_fallback_used", False),
                    "clustering_algorithm_version": algorithm_version,
                    **feature_metrics,
                    "embedding_coverage": round(int(feature_metrics.get("embedding_success_count") or 0) / max(len(keep_photos), 1), 4),
                    "low_quality_chapter_count": sum(bool(item.get("clustering_needs_review")) for item in chapter_list),
                    "selected_k": len(chapter_list),
                    "auto_selected_k": next((
                        (item.get("clustering_explanation") or {}).get("auto_selected_k")
                        for item in chapter_list
                        if (item.get("clustering_explanation") or {}).get("auto_selected_k") is not None
                    ), len(chapter_list)),
                    "peak_k": next((
                        (item.get("clustering_explanation") or {}).get("peak_k")
                        for item in chapter_list
                        if (item.get("clustering_explanation") or {}).get("peak_k") is not None
                    ), len(chapter_list)),
                    "granularity": granularity,
                    "k_selection_stability": next((
                        (item.get("clustering_explanation") or {}).get("k_selection_stability")
                        for item in chapter_list
                        if (item.get("clustering_explanation") or {}).get("k_selection_stability") is not None
                    ), None),
                    "missing_capture_time_count": sum(photo.get("taken_at") is None for photo in photo_payloads),
                    "theme_profile_id": theme_context.get("profile_id"),
                    "theme_title": theme_context.get("title"),
                    "chapter_strategy": theme_context.get("chapter_strategy"),
                    "theme_excluded_photo_count": len(excluded_ids),
                    "theme_relevance_coverage": theme_context.get("relevance_coverage", 0.0),
                    "llm_named_chapter_count": (debug_payload.get("naming") or {}).get("named_count", 0),
                    "chapter_naming_fallback_count": (debug_payload.get("naming") or {}).get("fallback_count", len(chapter_list)),
                    "representative_photo_count": sum(
                        len((item.get("clustering_explanation") or {}).get("representative_photo_ids", []))
                        for item in chapter_list
                    ),
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
