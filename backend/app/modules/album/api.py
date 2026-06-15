from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.common.enums import AlbumStatus
from app.common.responses import success_response
from app.storage.memory_store import memory_store

router = APIRouter(prefix="/albums", tags=["albums"])


class CreateAlbumPayload(BaseModel):
    name: str
    album_type: str = "yearbook"
    book_size: str = "square_10inch"
    theme_style: str = "minimal"
    cover_title: str | None = None


class UpdateAlbumPayload(BaseModel):
    name: str | None = None
    cover_title: str | None = None
    theme_style: str | None = None


@router.get("")
def list_albums() -> dict:
    return success_response(memory_store.list_albums())


@router.post("")
def create_album(payload: CreateAlbumPayload) -> dict:
    album = memory_store.create_album(payload.model_dump())
    return success_response(album, "album created")


@router.get("/{album_id}")
def get_album(album_id: str) -> dict:
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(album)


@router.patch("/{album_id}")
def update_album(album_id: str, payload: UpdateAlbumPayload) -> dict:
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")

    updates = payload.model_dump(exclude_none=True)
    updated = memory_store.update_album(album_id, updates)
    return success_response(updated, "album updated")


@router.delete("/{album_id}")
def delete_album(album_id: str) -> dict:
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")

    del memory_store.albums[album_id]
    memory_store.photos.pop(album_id, None)
    memory_store.chapters.pop(album_id, None)
    memory_store.pages.pop(album_id, None)
    memory_store.exports.pop(album_id, None)

    return success_response(None, "album deleted")


@router.get("/{album_id}/summary")
def get_album_summary(album_id: str) -> dict:
    """获取相册完整摘要（含照片/章节/页面/导出统计）。"""
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")

    return success_response({
        "album": album,
        "photo_count": len(memory_store.list_photos(album_id)),
        "chapter_count": len(memory_store.list_chapters(album_id)),
        "page_count": len(memory_store.list_pages(album_id)),
        "export_count": len(memory_store.list_exports(album_id)),
    })


@router.get("/{album_id}/chapters")
def list_album_chapters(album_id: str) -> dict:
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(memory_store.list_chapters(album_id))


@router.get("/{album_id}/pages")
def list_album_pages(album_id: str) -> dict:
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(memory_store.list_pages(album_id))


@router.get("/{album_id}/exports")
def list_album_exports(album_id: str) -> dict:
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(memory_store.list_exports(album_id))
