from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.repositories.album_repo import AlbumRepository
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.theme_curation_repo import ThemeCurationRepository
from app.services.photo_selection import requires_photo_review
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_theme_profile
from app.services.task_service import TaskService
from app.services.theme_workspace_builder import ThemeWorkspaceBuilder


THEME_ANALYSIS_TASK = "analyze_album_theme"
THEME_SELECTION_TASK = "score_album_theme"
THEME_ANALYSIS_JOB = "run_theme_analysis_job"
THEME_SELECTION_JOB = "run_theme_selection_job"
THEME_PIPELINE_NAME = "theme-curation"
CHAPTER_STRATEGIES = {"balanced", "activity_first", "time_first", "location_first"}


class ThemeRebuildConfirmationError(RuntimeError):
    def __init__(self, chapter_count: int) -> None:
        self.chapter_count = chapter_count
        super().__init__("theme change requires chapter rebuild confirmation")


class ThemeProfileStateError(RuntimeError):
    pass


class ThemeReviewUnresolvedError(ThemeProfileStateError):
    def __init__(self, review_count: int) -> None:
        self.review_count = review_count
        super().__init__(f"{review_count} photos require theme review decisions")


class ThemeCurationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.chapter_repo = ChapterRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.repo = ThemeCurationRepository(session)
        self.task_service = TaskService(session)
        self.render_artifacts = RenderArtifactService()
        self.workspace_builder = ThemeWorkspaceBuilder(session, CHAPTER_STRATEGIES)

    async def request_analysis(self, album_id: str, user_id: str | None, *, custom_theme: str | None = None):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        if album.status in {AlbumStatus.DRAFT, AlbumStatus.UPLOADED}:
            raise ThemeProfileStateError("photo cleaning must be completed before theme analysis")
        photos = await self.photo_repo.list_photos(album_id)
        pending_count = sum(requires_photo_review(photo) for photo in photos)
        if pending_count:
            raise ThemeProfileStateError(f"{pending_count} photos require cleaning review")
        custom_value = (custom_theme or "").strip()[:500] or None
        custom_hash = sha256((custom_value or "default").encode("utf-8")).hexdigest()[:12]
        settings = get_settings()
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=THEME_ANALYSIS_TASK,
            task_params={"custom_theme": custom_value},
            idempotency_key=f"theme-analysis:{album_id}:{album.content_revision}:{settings.theme_pipeline_version}:{custom_hash}",
            requested_revision=album.content_revision,
            resource_type="album",
            resource_id=album_id,
            job_name=THEME_ANALYSIS_JOB,
            pipeline_name=THEME_PIPELINE_NAME,
            pipeline_version=settings.theme_pipeline_version,
            max_attempts=settings.queue_max_attempts,
        )

    async def request_selection(
        self,
        album_id: str,
        user_id: str | None,
        *,
        profile_id: str,
        candidate_id: str,
        chapter_strategy: str,
        confirm_rebuild: bool = False,
    ):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        if chapter_strategy not in CHAPTER_STRATEGIES:
            raise ThemeProfileStateError("invalid chapter strategy")
        profile = await self.repo.get_profile(album_id, profile_id)
        if profile is None or profile.status not in {"candidates_ready", "review_pending"} or profile.analysis_revision != album.theme_input_revision:
            raise ThemeProfileStateError("theme candidates are stale")
        if not any(item.get("id") == candidate_id for item in profile.candidates_json or []):
            raise ThemeProfileStateError("theme candidate not found")
        chapters = await self.chapter_repo.list_chapters(album_id)
        if chapters and not confirm_rebuild:
            raise ThemeRebuildConfirmationError(len(chapters))
        settings = get_settings()
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=THEME_SELECTION_TASK,
            task_params={
                "profile_id": profile_id,
                "candidate_id": candidate_id,
                "chapter_strategy": chapter_strategy,
                "confirm_rebuild": confirm_rebuild,
            },
            idempotency_key=(
                f"theme-selection:{profile_id}:{candidate_id}:{chapter_strategy}:"
                f"{profile.selection_task_id or 'initial'}:{album.content_revision}:"
                f"{settings.theme_pipeline_version}"
            ),
            requested_revision=album.content_revision,
            resource_type="theme_profile",
            resource_id=profile_id,
            job_name=THEME_SELECTION_JOB,
            pipeline_name=THEME_PIPELINE_NAME,
            pipeline_version=settings.theme_pipeline_version,
            max_attempts=settings.queue_max_attempts,
        )

    async def workspace(self, album_id: str):
        return await self.workspace_builder.build(album_id)

    async def update_decisions(self, album_id: str, photo_ids: list[str], decision: str | None):
        if decision not in {None, "keep", "exclude"}:
            raise ThemeProfileStateError("invalid theme decision")
        profile = await self.repo.latest_profile(album_id)
        if profile is None or profile.status != "review_pending":
            raise ThemeProfileStateError("theme review is not pending")
        changed = await self.repo.update_decisions(profile, photo_ids, decision)
        await self.session.commit()
        return {"updated_count": changed}

    async def reopen_review(self, album_id: str, *, confirm_rebuild: bool = False):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        profile = await self.repo.latest_profile(album_id)
        if profile is None:
            raise ThemeProfileStateError("theme review is not available")
        if profile.status == "review_pending":
            return serialize_theme_profile(profile)
        if profile.status != "confirmed":
            raise ThemeProfileStateError("theme review is not available")
        chapters = await self.chapter_repo.list_chapters(album_id)
        if chapters and not confirm_rebuild:
            raise ThemeRebuildConfirmationError(len(chapters))
        if chapters and confirm_rebuild:
            album.content_revision += 1
            await self.album_repo.clear_album_pages(album_id)
            await self.album_repo.clear_album_chapters(album_id)
            await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)
            album.status = AlbumStatus.CLEANED
        profile.status = "review_pending"
        profile.confirmed_at = None
        profile.confirmed_revision = None
        await self.session.commit()
        return serialize_theme_profile(profile)

    async def confirm_review(self, album_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        profile = await self.repo.latest_profile(album_id)
        if profile is None or profile.status != "review_pending" or profile.analysis_revision != album.theme_input_revision:
            raise ThemeProfileStateError("theme review is not ready to confirm")
        unresolved = await self.repo.count_unresolved_reviews(profile.id)
        if unresolved:
            raise ThemeReviewUnresolvedError(unresolved)
        album.content_revision += 1
        profile.status = "confirmed"
        profile.confirmed_revision = album.theme_input_revision
        profile.confirmed_at = datetime.now(UTC)
        await self.session.commit()
        return serialize_theme_profile(profile)

    async def confirmed_context(self, album_id: str, theme_input_revision: int) -> dict[str, Any] | None:
        if not get_settings().theme_curation_enabled:
            return {
                "profile_id": None,
                "title": "完整记录",
                "chapter_strategy": "balanced",
                "constraints": {},
                "excluded_photo_ids": set(),
                "review_photo_ids": set(),
                "relevance_coverage": 0.0,
            }
        profile = await self.repo.confirmed_profile(album_id, theme_input_revision)
        if profile is None:
            return None
        assessments = await self.repo.list_assessments(profile.id)
        return {
            "profile_id": profile.id,
            "title": profile.title or "完整记录",
            "chapter_strategy": profile.chapter_strategy,
            "constraints": dict(profile.constraints_json or {}),
            "excluded_photo_ids": {
                item.photo_id for item in assessments if (item.user_decision or item.suggested_decision) == "exclude"
            },
            "review_photo_ids": {
                item.photo_id for item in assessments if (item.user_decision or item.suggested_decision) == "review"
            },
            "relevance_coverage": round(len(assessments) / max(len(await self.photo_repo.list_photos(album_id)), 1), 4),
        }
