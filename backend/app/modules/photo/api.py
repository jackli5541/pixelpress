from datetime import datetime, UTC
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.common.responses import success_response
from app.storage.file_store import get_album_upload_dir
from app.storage.memory_store import memory_store


class UpdatePhotoPayload(BaseModel):
    cleaning_recommendation: str | None = None  # "keep" | "remove"
    custom_caption: str | None = None
    scene_tags: list[str] | None = None

router = APIRouter(prefix="/albums/{album_id}/photos", tags=["photos"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"}


@router.get("")
def list_photos(album_id: str, recommendation: str = "all") -> dict:
    """列出照片。recommendation 参数：
    - "all"（默认）：返回全部照片
    - "keep"：仅返回建议保留的照片（cleaning_recommendation 为 "keep" 或 null）
    - "remove"：仅返回建议移除的照片
    """
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    photos = memory_store.list_photos(album_id)

    if recommendation == "keep":
        photos = [p for p in photos if p.get("cleaning_recommendation") != "remove"]
    elif recommendation == "remove":
        photos = [p for p in photos if p.get("cleaning_recommendation") == "remove"]

    return success_response({
        "album_id": album_id,
        "count": len(photos),
        "items": photos,
    })


@router.get("/{photo_id}")
def get_photo(album_id: str, photo_id: str) -> dict:
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    photo = memory_store.get_photo(album_id, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")

    return success_response(photo)


@router.post("/upload")
async def upload_photos(album_id: str, files: list[UploadFile] = File(...)) -> dict:
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")

    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    album_dir = get_album_upload_dir(album_id)
    uploaded_items: list[dict] = []
    rejected_items: list[dict] = []

    for file in files:
        original_name = file.filename or "untitled"
        suffix = Path(original_name).suffix.lower()
        content_type = file.content_type or ""

        if suffix not in ALLOWED_IMAGE_EXTENSIONS and not content_type.startswith("image/"):
            rejected_items.append({
                "filename": original_name,
                "reason": f"unsupported file type: {suffix}",
            })
            await file.close()
            continue

        photo_id = str(uuid4())
        target_suffix = suffix or ".jpg"
        target_name = f"{photo_id}{target_suffix}"
        target_path = album_dir / target_name
        file_bytes = await file.read()
        target_path.write_bytes(file_bytes)
        file_size = len(file_bytes)
        await file.close()

        # 尝试读取图片尺寸（基础方法：从文件头解析）
        width, height = _get_image_dimensions(target_path, suffix)

        photo_record = {
            "id": photo_id,
            "album_id": album_id,
            "filename": original_name,
            "content_type": content_type,
            "size": file_size,
            "width": width,
            "height": height,
            "storage_key": f"{album_id}/{target_name}",
            "url": f"/uploads/{album_id}/{target_name}",
            "uploaded_at": datetime.now(UTC).isoformat(),
        }
        uploaded_items.append(memory_store.add_photo(album_id, photo_record))

    return success_response({
        "album_id": album_id,
        "uploaded": uploaded_items,
        "rejected": rejected_items,
    }, "photos uploaded")


@router.patch("/{photo_id}")
def update_photo(album_id: str, photo_id: str, payload: UpdatePhotoPayload) -> dict:
    """更新照片元数据（清洗建议、说明文字、标签）。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    photo = memory_store.get_photo(album_id, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")

    updates = payload.model_dump(exclude_none=True)
    updated = memory_store.update_photo(album_id, photo_id, updates)
    return success_response(updated, "photo updated")


@router.delete("/{photo_id}")
def delete_photo(album_id: str, photo_id: str) -> dict:
    """从相册中删除一张照片。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    photo = memory_store.get_photo(album_id, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")

    # 删除磁盘文件
    album_dir = get_album_upload_dir(album_id)
    storage_key = photo.get("storage_key", "")
    file_name = Path(storage_key).name if storage_key else ""
    if file_name:
        file_path = album_dir / file_name
        if file_path.exists():
            file_path.unlink()

    memory_store.delete_photo(album_id, photo_id)
    return success_response(None, "photo deleted")


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
