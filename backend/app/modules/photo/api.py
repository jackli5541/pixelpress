from pathlib import Path

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.rate_limit import limiter
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.ownership import require_album_access
from app.common.responses import success_response
from app.db.session import get_db
from app.services.photo_service import PhotoService
from app.storage.file_store import get_file_storage


class UpdatePhotoPayload(BaseModel):
    cleaning_recommendation: str | None = None  # "keep" | "remove"
    custom_caption: str | None = None
    scene_tags: list[str] | None = None

router = APIRouter(prefix="/albums/{album_id}/photos", tags=["photos"])


def _validate_upload_request(files: list[UploadFile]) -> None:
    settings = get_settings()
    if len(files) > settings.upload_max_files_per_request:
        raise HTTPException(status_code=413, detail="too many files in upload request")


@router.get("")
async def list_photos(album_id: str, recommendation: str = "all", db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """列出照片。recommendation 参数：
    - "all"（默认）：返回全部照片
    - "keep"：仅返回建议保留的照片（cleaning_recommendation 为 "keep" 或 null）
    - "remove"：仅返回建议移除的照片
    """
    await require_album_access(db, user, album_id)
    service = PhotoService(db)
    payload = await service.list_photos(album_id, recommendation)
    if payload is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(payload)


@router.get("/{photo_id}")
async def get_photo(album_id: str, photo_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    photo = await PhotoService(db).get_photo(album_id, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    return success_response(photo)


@router.post("/upload")
@limiter.limit(get_settings().rate_limit_upload, key_func=get_remote_address)
async def upload_photos(request: Request, album_id: str, files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")
    _validate_upload_request(files)
    try:
        payload = await PhotoService(db).upload_photos(album_id, files)
    except ValueError as exc:
        if str(exc) == "upload batch too large":
            raise HTTPException(status_code=413, detail="upload batch too large") from exc
        raise
    if payload is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(payload, "photos uploaded")


@router.patch("/{photo_id}")
async def update_photo(album_id: str, photo_id: str, payload: UpdatePhotoPayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """更新照片元数据（清洗建议、说明文字、标签）。"""
    await require_album_access(db, user, album_id)
    updated = await PhotoService(db).update_photo(album_id, photo_id, payload.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="photo not found")
    return success_response(updated, "photo updated")


@router.delete("/{photo_id}")
async def delete_photo(album_id: str, photo_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """从相册中删除一张照片。"""
    await require_album_access(db, user, album_id)
    deleted = await PhotoService(db).delete_photo(album_id, photo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="photo not found")
    return success_response(None, "photo deleted")


@router.get("/{photo_id}/content")
async def get_photo_content(album_id: str, photo_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> Response:
    await require_album_access(db, user, album_id)
    photo = await PhotoService(db).get_photo(album_id, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    try:
        content = await get_file_storage().open_file(photo["storage_key"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="photo content not found") from None
    except Exception:
        raise HTTPException(status_code=502, detail="photo content unavailable") from None
    return Response(content=content, media_type=photo.get("content_type") or "application/octet-stream")


def _get_image_dimensions(file_path: Path, suffix: str) -> tuple[int | None, int | None]:
    """从文件头解析图片尺寸（轻量级，不依赖 Pillow）。"""
    try:
        if suffix in (".jpg", ".jpeg"):
            return _jpeg_dimensions(file_path)
        elif suffix == ".png":
            return _png_dimensions(file_path)
        elif suffix == ".gif":
            return _gif_dimensions(file_path)
        elif suffix == ".bmp":
            return _bmp_dimensions(file_path)
    except Exception:
        pass
    return None, None


def _jpeg_dimensions(path: Path) -> tuple[int, int] | tuple[None, None]:
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None, None
        while True:
            marker = f.read(2)
            if not marker or len(marker) < 2:
                return None, None
            if marker[0] != 0xFF:
                return None, None
            if 0xC0 <= marker[1] <= 0xC3 or marker[1] == 0xC9 or marker[1] == 0xCA:
                f.read(3)  # skip length + precision
                h = int.from_bytes(f.read(2), "big")
                w = int.from_bytes(f.read(2), "big")
                return w, h
            length = int.from_bytes(f.read(2), "big")
            f.read(length - 2)


def _png_dimensions(path: Path) -> tuple[int, int] | tuple[None, None]:
    with open(path, "rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            return None, None
        f.read(4)  # IHDR length
        if f.read(4) != b"IHDR":
            return None, None
        w = int.from_bytes(f.read(4), "big")
        h = int.from_bytes(f.read(4), "big")
        return w, h


def _gif_dimensions(path: Path) -> tuple[int, int] | tuple[None, None]:
    with open(path, "rb") as f:
        if f.read(6) not in (b"GIF89a", b"GIF87a"):
            return None, None
        w = int.from_bytes(f.read(2), "little")
        h = int.from_bytes(f.read(2), "little")
        return w, h


def _bmp_dimensions(path: Path) -> tuple[int, int] | tuple[None, None]:
    with open(path, "rb") as f:
        if f.read(2) != b"BM":
            return None, None
        f.read(16)  # skip to dimensions
        w = int.from_bytes(f.read(4), "little")
        h = int.from_bytes(f.read(4), "little")
        return w, h
