from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from app.storage.file_store import get_uploads_root
from app.storage.models import StoredFile


class LocalFileStorage:
    def get_uploads_root(self) -> Path:
        return get_uploads_root()

    def resolve_public_path(self, relative_path: str) -> Path:
        return self.get_uploads_root() / relative_path

    async def save_photo(
        self,
        album_id: str,
        photo_id: str,
        original_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile:
        suffix = Path(original_name).suffix.lower() or ".jpg"
        file_name = f"{photo_id}{suffix}"
        relative_path = f"albums/{album_id}/photos/{file_name}"
        target_path = self.resolve_public_path(relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return StoredFile(
            storage_key=relative_path,
            content_type=content_type,
            size=len(content),
            internal_path=str(target_path),
            public_url=None,
        )

    async def save_export(
        self,
        album_id: str,
        export_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile:
        relative_path = f"albums/{album_id}/exports/{export_name}"
        target_path = self.resolve_public_path(relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return StoredFile(
            storage_key=relative_path,
            content_type=content_type,
            size=len(content),
            internal_path=str(target_path),
            public_url=None,
        )

    async def save_export_from_path(
        self,
        album_id: str,
        export_name: str,
        source_path: Path,
        content_type: str,
    ) -> StoredFile:
        relative_path = f"albums/{album_id}/exports/{export_name}"
        target_path = self.resolve_public_path(relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source_path, target_path)
        return StoredFile(
            storage_key=relative_path,
            content_type=content_type,
            size=source_path.stat().st_size,
            internal_path=str(target_path),
            public_url=None,
        )

    async def save_artifact(
        self,
        album_id: str,
        artifact_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile:
        relative_path = f"albums/{album_id}/artifacts/{artifact_name}"
        target_path = self.resolve_public_path(relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return StoredFile(
            storage_key=relative_path,
            content_type=content_type,
            size=len(content),
            internal_path=str(target_path),
            public_url=None,
        )

    async def delete_file(self, storage_key: str) -> None:
        file_path = self.resolve_public_path(storage_key)
        if file_path.exists():
            file_path.unlink()

    async def open_file(self, storage_key: str) -> bytes:
        file_path = self.resolve_public_path(storage_key)
        return file_path.read_bytes()

    async def copy_to_path(self, storage_key: str, target_path: Path) -> None:
        source_path = self.resolve_public_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source_path, target_path)

    def build_photo_access_path(self, album_id: str, photo_id: str) -> str:
        return f"/api/v1/albums/{album_id}/photos/{photo_id}/content"
