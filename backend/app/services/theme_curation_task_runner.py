from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ImagePayload
from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.engines.chapter_engine.image_payloads import encode_image_payload
from app.engines.theme_pipeline import (
    build_theme_query_spec,
    complete_record_candidate,
    generate_theme_candidates,
    normalize_theme_constraints,
    selected_theme_text,
    summarize_theme_features,
)
from app.engines.theme_relevance_engine import ThemeQuery, ThemeRelevanceEngine, load_calibration
from app.repositories.album_repo import AlbumRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.theme_curation_repo import ThemeCurationRepository
from app.services.chapter_feature_service import ChapterFeatureService
from app.services.photo_selection import is_photo_included
from app.services.project_ai_config_service import ProjectAIConfigService
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_theme_profile
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_service import TaskService
from app.storage.file_store import get_file_storage


class ThemeCurationTaskRunner:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.repo = ThemeCurationRepository(session)
        self.feature_service = ChapterFeatureService(session)
        self.relevance_engine = ThemeRelevanceEngine()
        self.ai_config_service = ProjectAIConfigService(session)
        self.task_service = TaskService(session)
        self.runtime = TaskRuntimeService(self.task_service)
        self.render_artifacts = RenderArtifactService()

    async def execute_analysis(self, task_id: str, album_id: str, *, custom_theme: str | None = None):  # noqa: ANN201
        started = datetime.now(UTC)
        settings = get_settings()
        if not custom_theme:
            task = await self.task_service.get_task_model(task_id)
            custom_theme = str((task.task_params or {}).get("custom_theme") or "").strip() or None if task else None
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.content_revision)
            await self.runtime.heartbeat_step(task_id, "loading_theme_photos", 10)
            photos = [photo for photo in await self.photo_repo.list_photos(album_id) if is_photo_included(photo)]
            features: dict[str, dict] = {}
            feature_metrics: dict[str, Any] = {"degraded_photo_count": len(photos)}
            candidates: list[dict[str, Any]] = []
            provider = None
            model = None
            fallback_reason = None
            candidate_shortfall = False
            if settings.theme_curation_enabled and settings.ai_enabled and photos:
                await self.runtime.heartbeat_step(task_id, "extracting_theme_features", 25)
                try:
                    features, feature_metrics = await self.feature_service.extract(album_id, photos)
                    if features:
                        connection = await self.ai_config_service.resolve_for_album(
                            album_id,
                            stage="chapter",
                            model_hint=settings.ai_model_b2,
                            provider_hint=settings.ai_provider_b2,
                        )
                        images = await self._representative_images(photos)
                        feature_summary = summarize_theme_features(features)
                        candidates, debug = await generate_theme_candidates(
                            feature_summary,
                            images=images,
                            candidate_count=settings.theme_candidate_count,
                            provider_connection=connection,
                            custom_theme=custom_theme,
                        )
                        provider, model = debug.get("provider"), debug.get("model")
                        if len(candidates) < settings.theme_candidate_count:
                            retry_candidates, retry_debug = await generate_theme_candidates(
                                feature_summary,
                                images=images,
                                candidate_count=settings.theme_candidate_count - len(candidates),
                                provider_connection=connection,
                                custom_theme=custom_theme,
                                excluded_titles={item["title"] for item in candidates},
                            )
                            by_title = {item["title"].strip().lower(): item for item in candidates}
                            for item in retry_candidates:
                                by_title.setdefault(item["title"].strip().lower(), item)
                            candidates = list(by_title.values())[: settings.theme_candidate_count]
                            provider = retry_debug.get("provider") or provider
                            model = retry_debug.get("model") or model
                        candidate_shortfall = len(candidates) < settings.theme_candidate_count
                    else:
                        fallback_reason = "semantic_features_unavailable"
                except Exception as exc:  # noqa: BLE001
                    fallback_reason = str(exc)[:255]
            else:
                fallback_reason = "theme_ai_disabled"
            candidates = candidates[: settings.theme_candidate_count]
            candidates.append(complete_record_candidate())
            profile = await self.repo.create_profile({
                "album_id": album_id,
                "analysis_task_id": task_id,
                "analysis_revision": album.theme_input_revision,
                "confirmed_revision": None,
                "profile_version": settings.theme_pipeline_version,
                "source": "custom" if custom_theme else "analysis",
                "status": "candidates_ready",
                "title": None,
                "constraints_json": {},
                "candidates_json": candidates,
                "chapter_strategy": "balanced",
                "fallback_used": bool(fallback_reason),
                "custom_input": (custom_theme or "").strip() or None,
                "provider": provider,
                "model": model,
            })
            await self.task_service.complete_success(
                task_id,
                result_payload={"profile_id": profile.id, "candidate_count": len(candidates)},
                metrics_payload={
                    "duration_ms": round((datetime.now(UTC) - started).total_seconds() * 1000),
                    "photo_count": len(photos),
                    "candidate_count": len(candidates),
                    "fallback_used": bool(fallback_reason),
                    "candidate_shortfall": candidate_shortfall,
                    **feature_metrics,
                },
                debug_payload={"fallback_reason": fallback_reason, "candidate_shortfall": candidate_shortfall},
                result_revision=album.content_revision,
            )
            await self.session.commit()
            return serialize_theme_profile(profile)
        except RuntimeError as exc:
            await self.task_service.complete_failure(
                task_id,
                error_code="stale_task" if "stale" in str(exc) else "task_cancelled",
                error_message=str(exc),
                retryable=False,
            )
            await self.session.commit()
            return None
        except Exception as exc:  # noqa: BLE001
            await self.task_service.complete_failure(
                task_id,
                error_code="theme_analysis_failed",
                error_message=str(exc)[:500],
                retryable=False,
            )
            await self.session.commit()
            return None

    async def execute_selection(
        self,
        task_id: str,
        album_id: str,
        *,
        profile_id: str,
        candidate_id: str,
        chapter_strategy: str,
        confirm_rebuild: bool = False,
    ):  # noqa: ANN201
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.content_revision)
            profile = await self.repo.get_profile(album_id, profile_id)
            if profile is None:
                raise RuntimeError("theme profile not found")
            candidate = next((item for item in profile.candidates_json or [] if item.get("id") == candidate_id), None)
            if candidate is None:
                raise RuntimeError("theme candidate not found")
            selected_theme = selected_theme_text(candidate, profile.custom_input)
            await self.runtime.heartbeat_step(task_id, "scoring_theme_relevance", 25)
            if confirm_rebuild:
                album.content_revision += 1
                await self.album_repo.clear_album_pages(album_id)
                await self.album_repo.clear_album_chapters(album_id)
                await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)
                album.status = AlbumStatus.CLEANED
            photos = [photo for photo in await self.photo_repo.list_photos(album_id) if is_photo_included(photo)]
            features: dict[str, dict] = {}
            query: ThemeQuery | None = None
            if get_settings().theme_curation_enabled and candidate_id != "complete_record":
                try:
                    features, _ = await self.feature_service.extract(album_id, photos)
                except Exception:  # noqa: BLE001
                    features = {}
                try:
                    concept_connection = await self.ai_config_service.resolve_for_album(
                        album_id,
                        stage="chapter",
                        model_hint=get_settings().ai_model_b2,
                        provider_hint=get_settings().ai_provider_b2,
                    )
                    query_spec = await build_theme_query_spec(candidate, raw_theme=selected_theme, connection=concept_connection)
                    embedding_connection = await self.feature_service.resolve_embedding_connection()
                    query = await self.relevance_engine.build_query(
                        {**candidate, "_query_spec": query_spec},
                        connection=embedding_connection,
                        dimension=get_settings().chapter_embedding_dimension,
                        custom_input=selected_theme,
                    )
                except Exception:  # noqa: BLE001
                    query = None
            calibration = load_calibration(get_settings().theme_relevance_calibration_path)
            explicit_constraints = normalize_theme_constraints(
                {},
                custom_theme=profile.custom_input if candidate.get("source") == "custom" else None,
            )
            scoring_candidate = {**candidate, "explicit_constraints": explicit_constraints}
            assessments = [
                self.relevance_engine.score_record(
                    photo_id=photo.id,
                    taken_at=getattr(photo, "taken_at", None),
                    feature=features.get(photo.id),
                    candidate=scoring_candidate,
                    query=query,
                    calibration=calibration,
                )
                for photo in photos
            ]
            await self.repo.supersede_active_profiles(album_id, except_profile_id=profile.id)
            await self.repo.replace_assessments(profile, assessments)
            await self.repo.update_profile(profile, {
                "selection_task_id": task_id,
                "source": candidate.get("source", "ai"),
                "status": "review_pending",
                "title": candidate.get("title"),
                "constraints_json": explicit_constraints,
                "chapter_strategy": chapter_strategy,
            })
            await self.task_service.complete_success(
                task_id,
                result_payload={
                    "profile_id": profile.id,
                    "review_photo_count": sum(item["suggested_decision"] == "review" for item in assessments),
                    "suggested_exclude_count": sum(item["suggested_decision"] == "exclude" for item in assessments),
                    "auto_decision_enabled": any(
                        (item.get("evidence_json") or {}).get("calibration_status") == "ready"
                        for item in assessments
                    ),
                },
                result_revision=album.content_revision,
            )
            await self.session.commit()
            return serialize_theme_profile(profile)
        except Exception as exc:  # noqa: BLE001
            await self.task_service.complete_failure(
                task_id,
                error_code="theme_selection_failed",
                error_message=str(exc)[:500],
                retryable=False,
            )
            await self.session.commit()
            return None

    async def _representative_images(self, photos: list[Any]) -> list[ImagePayload]:
        storage = get_file_storage()
        images: list[ImagePayload] = []
        ranked = sorted(photos, key=lambda photo: (-(float(photo.quality_score or 0)), photo.id))[:6]
        for photo in ranked:
            try:
                content = await storage.open_file(photo.storage_key)
                images.append(encode_image_payload(content, filename=photo.filename, max_edge=1024, quality=82))
            except Exception:  # noqa: BLE001
                continue
        return images
