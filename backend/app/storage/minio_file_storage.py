from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings
from app.storage.models import StoredFile


class MinioFileStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.minio_bucket
        self.public_base_url = settings.minio_public_base_url
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        found = self.client.bucket_exists(self.bucket)
        if not found:
            self.client.make_bucket(self.bucket)

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
        object_name = f"albums/{album_id}/photos/{file_name}"
        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        return StoredFile(
            storage_key=object_name,
            content_type=content_type or "application/octet-stream",
            size=len(content),
            internal_path=None,
            public_url=f"{self.public_base_url.rstrip('/')}/{self.bucket}/{object_name}" if self.public_base_url else None,
        )

    async def save_export(
        self,
        album_id: str,
        export_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile:
        object_name = f"albums/{album_id}/exports/{export_name}"
        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        return StoredFile(
            storage_key=object_name,
            content_type=content_type or "application/octet-stream",
            size=len(content),
            internal_path=None,
            public_url=f"{self.public_base_url.rstrip('/')}/{self.bucket}/{object_name}" if self.public_base_url else None,
        )

    async def save_export_from_path(
        self,
        album_id: str,
        export_name: str,
        source_path: Path,
        content_type: str,
    ) -> StoredFile:
        object_name = f"albums/{album_id}/exports/{export_name}"
        await asyncio.to_thread(
            self.client.fput_object,
            self.bucket,
            object_name,
            str(source_path),
            content_type=content_type or "application/octet-stream",
        )
        return StoredFile(
            storage_key=object_name,
            content_type=content_type or "application/octet-stream",
            size=source_path.stat().st_size,
            internal_path=None,
            public_url=f"{self.public_base_url.rstrip('/')}/{self.bucket}/{object_name}" if self.public_base_url else None,
        )

    async def save_artifact(
        self,
        album_id: str,
        artifact_name: str,
        content: bytes,
        content_type: str,
    ) -> StoredFile:
        object_name = f"albums/{album_id}/artifacts/{artifact_name}"
        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        return StoredFile(
            storage_key=object_name,
            content_type=content_type or "application/octet-stream",
            size=len(content),
            internal_path=None,
            public_url=f"{self.public_base_url.rstrip('/')}/{self.bucket}/{object_name}" if self.public_base_url else None,
        )

    async def delete_file(self, storage_key: str) -> None:
        try:
            self.client.remove_object(self.bucket, storage_key)
        except S3Error as exc:
            if exc.code != "NoSuchKey":
                raise

    async def open_file(self, storage_key: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket, storage_key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchBucket"}:
                raise FileNotFoundError(storage_key) from exc
            raise
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def copy_to_path(self, storage_key: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(self.client.fget_object, self.bucket, storage_key, str(target_path))
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchBucket"}:
                raise FileNotFoundError(storage_key) from exc
            raise

    def build_photo_access_path(self, album_id: str, photo_id: str) -> str:
        return f"/api/v1/albums/{album_id}/photos/{photo_id}/content"
