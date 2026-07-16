from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.repositories.album_repo import AlbumRepository
from app.repositories.photo_repo import PhotoRepository
from app.services.photo_ingest import ProcessedUploadImage, process_uploaded_image
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_photo
from app.storage.file_store import get_file_storage

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"}
REJECT_REASON_UNSUPPORTED_TYPE = "unsupported file type"
REJECT_REASON_FILE_TOO_LARGE = "file too large"
REJECT_REASON_IMAGE_TOO_LARGE = "image exceeds pixel limit"
REJECT_REASON_INVALID_DIMENSIONS = "unable to validate image dimensions"


class PhotoService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.storage = get_file_storage()
        self.render_artifacts = RenderArtifactService()

    async def _clear_render_artifacts(self, album) -> None:
        await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.UPLOADED)

    async def _read_upload_file_with_limit(self, file: UploadFile, *, max_file_size_bytes: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_file_size_bytes:
                raise ValueError(REJECT_REASON_FILE_TOO_LARGE)
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _validate_image_pixel_limit(*, width: int | None, height: int | None, max_pixels: int) -> None:
        if width is None or height is None:
            raise ValueError(REJECT_REASON_INVALID_DIMENSIONS)
        if width * height > max_pixels:
            raise ValueError(REJECT_REASON_IMAGE_TOO_LARGE)

    async def list_photos(self, album_id: str, recommendation: str = "all"):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        photos = await self.photo_repo.list_photos(album_id)
        serialized = [serialize_photo(photo) for photo in photos]
        if recommendation == "keep":
            serialized = [p for p in serialized if p.get("cleaning", {}).get("decision") != "remove"]
        elif recommendation == "remove":
            serialized = [p for p in serialized if p.get("cleaning", {}).get("decision") == "remove"]
        return {"album_id": album_id, "count": len(serialized), "items": serialized}

    async def get_photo(self, album_id: str, photo_id: str):
        photo = await self.photo_repo.get_photo(album_id, photo_id)
        if photo is None:
            return None
        return serialize_photo(photo)

    async def upload_photos(self, album_id: str, files: list[UploadFile]):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        settings = get_settings()
        uploaded_items: list[dict] = []
        rejected_items: list[dict] = []
        batch_size = 0

        for file in files:
            original_name = file.filename or "untitled"
            suffix = Path(original_name).suffix.lower()
            content_type = file.content_type or ""

            if suffix not in ALLOWED_IMAGE_EXTENSIONS or (content_type and not content_type.startswith("image/")):
                rejected_items.append({"filename": original_name, "reason": REJECT_REASON_UNSUPPORTED_TYPE})
                await file.close()
                continue

            try:
                file_bytes = await self._read_upload_file_with_limit(
                    file,
                    max_file_size_bytes=settings.upload_max_file_size_bytes,
                )
            except ValueError as exc:
                rejected_items.append({"filename": original_name, "reason": str(exc)})
                continue
            finally:
                await file.close()

            try:
                processed = process_uploaded_image(
                    content=file_bytes,
                    original_name=original_name,
                    content_type=content_type,
                )
            except Exception:
                rejected_items.append({"filename": original_name, "reason": REJECT_REASON_INVALID_DIMENSIONS})
                continue

            if len(processed.content) > settings.upload_max_file_size_bytes:
                rejected_items.append({"filename": original_name, "reason": REJECT_REASON_FILE_TOO_LARGE})
                continue

            batch_size += len(processed.content)
            if batch_size > settings.upload_max_batch_size_bytes:
                raise ValueError("upload batch too large")

            try:
                self._validate_image_pixel_limit(
                    width=processed.width,
                    height=processed.height,
                    max_pixels=settings.upload_max_image_pixels,
                )
            except ValueError as exc:
                rejected_items.append({"filename": original_name, "reason": str(exc)})
                continue

            photo_id = str(uuid4())
            stored = await self.storage.save_photo(
                album_id,
                photo_id,
                processed.filename,
                processed.content,
                processed.content_type,
            )
            photo = await self.photo_repo.create_photo(self._build_photo_payload(
                album_id=album_id,
                photo_id=photo_id,
                processed=processed,
                storage_key=stored.storage_key,
            ))
            uploaded_items.append(serialize_photo(photo))

        album.photo_count = len(await self.photo_repo.list_photos(album_id))
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        album.status = AlbumStatus.UPLOADED
        await self.session.commit()
        return {"album_id": album_id, "uploaded": uploaded_items, "rejected": rejected_items}

    @staticmethod
    def _build_photo_payload(*, album_id: str, photo_id: str, processed: ProcessedUploadImage, storage_key: str) -> dict:
        return {
            "id": photo_id,
            "album_id": album_id,
            "filename": processed.filename,
            "content_type": processed.content_type,
            "size": len(processed.content),
            "width": processed.width,
            "height": processed.height,
            "storage_key": storage_key,
            "url": get_file_storage().build_photo_access_path(album_id, photo_id),
            "uploaded_at": datetime.now(UTC),
            "taken_at": processed.taken_at,
            "taken_timezone": processed.taken_timezone,
            "gps_latitude": processed.gps_latitude,
            "gps_longitude": processed.gps_longitude,
            "device_model": processed.device_model,
        }

    async def update_photo(self, album_id: str, photo_id: str, updates: dict):
        photo = await self.photo_repo.get_photo(album_id, photo_id)
        if photo is None:
            return None
        updated = await self.photo_repo.update_photo(photo, updates)
        album = await self.album_repo.get_album(album_id)
        if album is not None:
            album.content_revision += 1
            await self._clear_render_artifacts(album)
        await self.session.commit()
        return serialize_photo(updated)

    async def delete_photo(self, album_id: str, photo_id: str) -> bool:
        photo = await self.photo_repo.get_photo(album_id, photo_id)
        if photo is None:
            return False
        if photo.storage_key:
            await self.storage.delete_file(photo.storage_key)
        await self.photo_repo.delete_photo(photo)
        album = await self.album_repo.get_album(album_id)
        if album is not None:
            album.photo_count = len(await self.photo_repo.list_photos(album_id))
            album.content_revision += 1
            await self._clear_render_artifacts(album)
        await self.session.commit()
        return True
