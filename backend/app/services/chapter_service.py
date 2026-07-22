from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.engines.chapter_engine.sequential_clusterer import ALGORITHM_VERSION
from app.repositories.album_repo import AlbumRepository
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.photo_repo import PhotoRepository
from app.services.photo_selection import requires_photo_review
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_chapter
from app.services.task_service import TaskService
from app.services.theme_curation_service import ThemeCurationService

PIPELINE_NAME = "chaptering"
TASK_TYPE = "cluster_chapters"
JOB_NAME = "run_cluster_chapters_job"


class PendingPhotoReviewError(Exception):
    def __init__(self, pending_review_count: int) -> None:
        self.pending_review_count = pending_review_count
        super().__init__(f"{pending_review_count} photos require review")


class ChapterRebuildConfirmationError(Exception):
    def __init__(self, chapter_count: int) -> None:
        self.chapter_count = chapter_count
        super().__init__(f"{chapter_count} existing chapters require rebuild confirmation")


class InvalidChapterPhotoError(Exception):
    def __init__(self, invalid_count: int) -> None:
        self.invalid_count = invalid_count
        super().__init__(f"{invalid_count} photo ids do not belong to the album")


class ThemeReviewRequiredError(RuntimeError):
    pass


def _manual_clustering_updates() -> dict[str, Any]:
    return {
        "clustering_source": "user",
        "clustering_algorithm_version": None,
        "clustering_quality": None,
        "clustering_needs_review": False,
        "clustering_explanation": None,
    }


class ChapterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.chapter_repo = ChapterRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.task_service = TaskService(session)
        self.render_artifacts = RenderArtifactService()
        self.theme_service = ThemeCurationService(session)

    async def _clear_render_artifacts(self, album) -> None:
        await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.CLEANED)

    async def _validate_photo_ids(self, album_id: str, photo_ids: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(str(photo_id) for photo_id in photo_ids))
        allowed_ids = {photo.id for photo in await self.photo_repo.list_photos(album_id)}
        invalid_count = sum(photo_id not in allowed_ids for photo_id in normalized)
        if invalid_count:
            raise InvalidChapterPhotoError(invalid_count)
        return normalized

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
        photo_ids = await self._validate_photo_ids(album_id, payload.get("photo_ids", []))
        existing = await self.chapter_repo.list_chapters(album_id)
        chapter = await self.chapter_repo.create_chapter(
            {
                "album_id": album_id,
                "name": payload.get("name", "新章节"),
                "description": payload.get("description", ""),
                "order_index": len(existing),
                **_manual_clustering_updates(),
            },
            photo_ids,
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
        if photo_ids is not None:
            photo_ids = await self._validate_photo_ids(album_id, photo_ids)
            payload.update(_manual_clustering_updates())
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
        photo_ids = await self._validate_photo_ids(album_id, photo_ids)
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
            updates = _manual_clustering_updates() if current_ids != [link.photo_id for link in sorted(chapter.photo_links, key=lambda item: item.order_index)] else {}
            await self.chapter_repo.update_chapter(chapter, updates, current_ids)
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
        await self.chapter_repo.update_chapter(target, _manual_clustering_updates(), target_ids)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        refreshed = await self.chapter_repo.get_chapter(album_id, target_id)
        return {"chapter": serialize_chapter(refreshed), "merged_photos": merged_count}, None

    async def request_cluster_chapters(
        self,
        album_id: str,
        user_id: str | None,
        *,
        confirm_rebuild: bool = False,
        granularity: int = 0,
    ) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        photos = await self.photo_repo.list_photos(album_id)
        pending_review_count = sum(requires_photo_review(photo) for photo in photos)
        if pending_review_count:
            raise PendingPhotoReviewError(pending_review_count)
        theme_context = await self.theme_service.confirmed_context(album_id, album.theme_input_revision)
        if theme_context is None:
            raise ThemeReviewRequiredError("theme review must be confirmed before clustering")
        if theme_context and theme_context.get("review_photo_ids"):
            raise ThemeReviewRequiredError("theme photo review is incomplete")
        existing_chapters = await self.chapter_repo.list_chapters(album_id)
        if existing_chapters and not confirm_rebuild:
            raise ChapterRebuildConfirmationError(len(existing_chapters))
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=TASK_TYPE,
            task_params={"confirm_rebuild": confirm_rebuild, "granularity": granularity},
            idempotency_key=f"cluster:{album_id}:{album.content_revision}:{ALGORITHM_VERSION}:{granularity}",
            requested_revision=album.content_revision,
            resource_type="album",
            resource_id=album_id,
            job_name=JOB_NAME,
            pipeline_name=PIPELINE_NAME,
            pipeline_version=ALGORITHM_VERSION,
            max_attempts=get_settings().queue_max_attempts,
        )
