from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.repositories.album_repo import AlbumRepository
from app.storage.file_store import get_file_storage
from app.services.project_service import ProjectService
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_album


class AlbumService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AlbumRepository(session)
        self.project_service = ProjectService(session)
        self.storage = get_file_storage()
        self.render_artifacts = RenderArtifactService()

    async def list_albums(self, *, user_id: str | None = None, is_admin: bool = False) -> list[dict]:
        albums = await self.repo.list_albums(user_id=user_id, is_admin=is_admin)
        touched = False
        for album in albums:
            if not album.project_id and album.user_id:
                await self.project_service.ensure_album_project(album)
                touched = True
        if touched:
            await self.session.commit()
        return [serialize_album(album) for album in albums]

    async def create_album(self, payload: dict, *, is_admin: bool = False) -> dict:
        user_id = payload.get("user_id")
        if payload.get("project_id") and user_id:
            allowed = await self.project_service.user_can_access_project(
                payload["project_id"],
                user_id=user_id,
                is_admin=is_admin,
            )
            if not allowed:
                raise ValueError("project not found or inaccessible")
        if not payload.get("project_id") and user_id:
            default_project = await self.project_service.ensure_default_project(user_id)
            payload["project_id"] = default_project["id"]
        payload.setdefault(
            "print_spec_json",
            payload.pop(
                "print_spec",
                {
                    "book_size": payload.get("book_size", "square_10inch"),
                    "bleed_mm": 3,
                    "safe_margin_mm": 8,
                    "page_dpi": 300,
                    "allow_spread": True,
                    "color_profile": "rgb",
                },
            ),
        )
        album = await self.repo.create_album(payload)
        await self.session.commit()
        return serialize_album(album)

    async def get_album(self, album_id: str):
        album = await self.repo.get_album(album_id)
        if album is None:
            return None
        await self.project_service.ensure_album_project(album)
        await self.session.commit()
        return serialize_album(album)

    async def get_album_model(self, album_id: str):
        album = await self.repo.get_album(album_id)
        if album is not None:
            await self.project_service.ensure_album_project(album)
            await self.session.flush()
        return album

    async def update_album(self, album_id: str, updates: dict):
        album = await self.repo.get_album(album_id)
        if album is None:
            return None
        if "print_spec" in updates:
            updates["print_spec_json"] = updates.pop("print_spec")

        render_affecting_fields = {"name", "cover_title", "theme_style", "book_size", "print_spec_json"}
        should_invalidate_render = False
        for field in render_affecting_fields:
            if field not in updates:
                continue
            if getattr(album, field) != updates[field]:
                should_invalidate_render = True
                break

        updated = await self.repo.update_album(album, updates)
        if should_invalidate_render:
            updated.content_revision += 1
            await clear_render_artifacts(updated, self.render_artifacts, stale_status=AlbumStatus.PLANNED)
        await self.session.flush()
        await self.session.refresh(updated)
        await self.session.commit()
        return serialize_album(updated)

    async def delete_album(self, album_id: str) -> bool:
        return await self.delete_album_deep(album_id)

    async def delete_album_deep(self, album_id: str) -> bool:
        album = await self.repo.get_album_with_assets(album_id)
        if album is None:
            return False
        try:
            await self.delete_album_model_deep(album)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return True

    async def delete_album_model_deep(self, album) -> None:
        photo_keys, extra_keys, export_keys = self._collect_album_storage_keys(album)
        await self._delete_album_storage_files(photo_keys, extra_keys, export_keys)
        await self.repo.delete_album(album.id)

    def _collect_album_storage_keys(self, album) -> tuple[list[str], list[str], list[str]]:
        photo_keys = [photo.storage_key for photo in getattr(album, "photos", []) if getattr(photo, "storage_key", None)]
        extra_keys = [
            key
            for key in [
                getattr(album, "preview_html_path", None),
                getattr(album, "print_html_path", None),
                getattr(album, "render_manifest_path", None),
            ]
            if key
        ]
        export_keys = [item.file_path for item in getattr(album, "exports", []) if getattr(item, "file_path", None)]
        return photo_keys, extra_keys, export_keys

    async def _delete_album_storage_files(self, photo_keys: list[str], extra_keys: list[str], export_keys: list[str]) -> None:
        for storage_key in photo_keys + extra_keys + export_keys:
            if not storage_key:
                continue
            try:
                await self.storage.delete_file(storage_key)
            except FileNotFoundError:
                continue

    async def get_summary(self, album_id: str):
        album = await self.repo.get_album(album_id)
        if album is None:
            return None
        counts = await self.repo.summary_counts(album_id)
        return {
            "album": serialize_album(album),
            **counts,
        }

    async def list_album_chapters(self, album_id: str):
        if await self.repo.get_album(album_id) is None:
            return None
        chapters = await self.repo.list_chapters(album_id)
        from app.services.serializers import serialize_chapter

        return [serialize_chapter(chapter) for chapter in chapters]

    async def list_album_pages(self, album_id: str):
        if await self.repo.get_album(album_id) is None:
            return None
        pages = await self.repo.list_pages(album_id)
        from app.services.serializers import serialize_page

        return [serialize_page(page) for page in pages]

    async def list_album_exports(self, album_id: str):
        if await self.repo.get_album(album_id) is None:
            return None
        exports = await self.repo.list_exports(album_id)
        from app.services.serializers import serialize_export

        return [serialize_export(item) for item in exports]
