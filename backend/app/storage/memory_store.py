from datetime import datetime, UTC
from typing import Any
from uuid import uuid4

from app.common.enums import AlbumStatus, TaskStatus


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class MemoryStore:
    def __init__(self) -> None:
        self.albums: dict[str, dict[str, Any]] = {}
        self.photos: dict[str, dict[str, dict[str, Any]]] = {}   # album_id -> photo_id -> photo
        self.tasks: dict[str, dict[str, Any]] = {}
        self.chapters: dict[str, dict[str, dict[str, Any]]] = {}  # album_id -> chapter_id -> chapter
        self.pages: dict[str, dict[str, dict[str, Any]]] = {}     # album_id -> page_id -> page
        self.page_photos: dict[str, list[str]] = {}               # page_id -> [photo_id, ...]
        self.exports: dict[str, dict[str, dict[str, Any]]] = {}   # album_id -> export_id -> export

    # ── Albums ──────────────────────────────────────────────

    def list_albums(self) -> list[dict[str, Any]]:
        return list(self.albums.values())

    def create_album(self, payload: dict[str, Any]) -> dict[str, Any]:
        album_id = str(uuid4())
        album = {
            "id": album_id,
            "name": payload["name"],
            "album_type": payload.get("album_type", "yearbook"),
            "book_size": payload.get("book_size", "square_10inch"),
            "theme_style": payload.get("theme_style", "minimal"),
            "cover_title": payload.get("cover_title"),
            "status": AlbumStatus.DRAFT,
            "photo_count": 0,
            "updated_at": utc_now_iso(),
        }
        self.albums[album_id] = album
        self.photos[album_id] = {}
        self.chapters[album_id] = {}
        self.pages[album_id] = {}
        self.exports[album_id] = {}
        return album

    def get_album(self, album_id: str) -> dict[str, Any] | None:
        return self.albums.get(album_id)

    def update_album(self, album_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        album = self.albums.get(album_id)
        if album is None:
            return None
        album.update(updates)
        album["updated_at"] = utc_now_iso()
        return album

    # ── Photos ──────────────────────────────────────────────

    def list_photos(self, album_id: str) -> list[dict[str, Any]]:
        return list(self.photos.get(album_id, {}).values())

    def get_photo(self, album_id: str, photo_id: str) -> dict[str, Any] | None:
        return self.photos.get(album_id, {}).get(photo_id)

    def add_photo(self, album_id: str, photo: dict[str, Any]) -> dict[str, Any]:
        self.photos.setdefault(album_id, {})
        self.photos[album_id][photo["id"]] = photo
        album = self.albums.get(album_id)
        if album is not None:
            album["photo_count"] = len(self.photos[album_id])
            album["status"] = AlbumStatus.UPLOADED
            album["updated_at"] = utc_now_iso()
        return photo

    def update_photo(self, album_id: str, photo_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        photo = self.photos.get(album_id, {}).get(photo_id)
        if photo is None:
            return None
        photo.update(updates)
        return photo

    def delete_photo(self, album_id: str, photo_id: str) -> bool:
        album_photos = self.photos.get(album_id, {})
        if photo_id not in album_photos:
            return False
        del album_photos[photo_id]
        album = self.albums.get(album_id)
        if album is not None:
            album["photo_count"] = len(album_photos)
            album["updated_at"] = utc_now_iso()
        return True

    # ── Tasks ───────────────────────────────────────────────

    def create_task(self, album_id: str, task_type: str) -> dict[str, Any]:
        task_id = str(uuid4())
        task = {
            "id": task_id,
            "album_id": album_id,
            "task_type": task_type,
            "task_status": TaskStatus.QUEUED,
            "created_at": utc_now_iso(),
        }
        self.tasks[task_id] = task
        album = self.albums.get(album_id)
        if album is not None:
            album["updated_at"] = utc_now_iso()
        return task

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        task.update(updates)
        return task

    def list_tasks(self, album_id: str | None = None) -> list[dict[str, Any]]:
        tasks = list(self.tasks.values())
        if album_id is not None:
            tasks = [t for t in tasks if t.get("album_id") == album_id]
        return tasks

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self.tasks.get(task_id)

    # ── Chapters ────────────────────────────────────────────

    def list_chapters(self, album_id: str) -> list[dict[str, Any]]:
        return list(self.chapters.get(album_id, {}).values())

    def create_chapter(self, album_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.chapters.setdefault(album_id, {})
        chapter_id = str(uuid4())
        chapter = {
            "id": chapter_id,
            "album_id": album_id,
            "name": payload.get("name", "Untitled"),
            "description": payload.get("description", ""),
            "order": len(self.chapters[album_id]) + 1,
            "photo_ids": payload.get("photo_ids", []),
            "created_at": utc_now_iso(),
        }
        self.chapters[album_id][chapter_id] = chapter
        return chapter

    def update_chapter(self, album_id: str, chapter_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        chapter = self.chapters.get(album_id, {}).get(chapter_id)
        if chapter is None:
            return None
        chapter.update(updates)
        return chapter

    # ── Pages ───────────────────────────────────────────────

    def list_pages(self, album_id: str) -> list[dict[str, Any]]:
        return list(self.pages.get(album_id, {}).values())

    def create_page(self, album_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.pages.setdefault(album_id, {})
        page_id = str(uuid4())
        page = {
            "id": page_id,
            "album_id": album_id,
            "chapter_id": payload.get("chapter_id"),
            "page_number": len(self.pages[album_id]) + 1,
            "template": payload.get("template", "grid_3"),
            "photo_ids": payload.get("photo_ids", []),
            "html": payload.get("html", ""),
            "status": "draft",
            "created_at": utc_now_iso(),
        }
        self.pages[album_id][page_id] = page
        self.page_photos[page_id] = list(payload.get("photo_ids", []))
        return page

    def update_page(self, album_id: str, page_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        page = self.pages.get(album_id, {}).get(page_id)
        if page is None:
            return None
        page.update(updates)
        return page

    def get_page_photos(self, page_id: str) -> list[str]:
        return self.page_photos.get(page_id, [])

    # ── Exports ─────────────────────────────────────────────

    def list_exports(self, album_id: str) -> list[dict[str, Any]]:
        return list(self.exports.get(album_id, {}).values())

    def create_export(self, album_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.exports.setdefault(album_id, {})
        export_id = str(uuid4())
        export = {
            "id": export_id,
            "album_id": album_id,
            "status": payload.get("status", "queued"),
            "file_path": payload.get("file_path"),
            "file_size": payload.get("file_size"),
            "task_id": payload.get("task_id", ""),
            "created_at": utc_now_iso(),
        }
        self.exports[album_id][export_id] = export
        return export


memory_store = MemoryStore()
