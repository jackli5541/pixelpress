from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.storage.models import StoredFile


class FileStorage(Protocol):
    async def save_photo(
        self,
        album_id: str,
        photo_id: str,
        original_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile: ...

    async def save_export(
        self,
        album_id: str,
        export_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile: ...

    async def save_artifact(
        self,
        album_id: str,
        artifact_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile: ...

    async def delete_file(self, storage_key: str) -> None: ...

    async def open_file(self, storage_key: str) -> bytes: ...

    def build_photo_access_path(self, album_id: str, photo_id: str) -> str: ...


def get_uploads_root() -> Path:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    uploads_root = backend_root / settings.uploads_dir
    uploads_root.mkdir(parents=True, exist_ok=True)
    return uploads_root


def get_album_upload_dir(album_id: str) -> Path:
    album_dir = get_uploads_root() / album_id
    album_dir.mkdir(parents=True, exist_ok=True)
    return album_dir


def get_file_storage() -> FileStorage:
    settings = get_settings()
    if settings.storage_backend == "minio":
        from app.storage.minio_file_storage import MinioFileStorage

        return MinioFileStorage()

    from app.storage.local_file_storage import LocalFileStorage

    return LocalFileStorage()
