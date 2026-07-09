from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.ownership import require_album_access
from app.common.responses import success_response
from app.db.session import get_db
from app.services.album_service import AlbumService
from app.services.task_service import TaskService

router = APIRouter(prefix="/albums", tags=["albums"])


class CreateAlbumPayload(BaseModel):
    name: str
    project_id: str | None = None
    album_type: str = "yearbook"
    book_size: str = "square_10inch"
    theme_style: str = "minimal"
    cover_title: str | None = None
    print_spec: dict | None = None


class UpdateAlbumPayload(BaseModel):
    name: str | None = None
    cover_title: str | None = None
    theme_style: str | None = None
    print_spec: dict | None = None


@router.get("")
async def list_albums(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    service = AlbumService(db)
    return success_response(await service.list_albums(user_id=user.id, is_admin=user.role == "admin"))


@router.post("")
async def create_album(payload: CreateAlbumPayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    service = AlbumService(db)
    try:
        album = await service.create_album(
            {**payload.model_dump(), "user_id": user.id},
            is_admin=user.role == "admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return success_response(album, "album created")


@router.get("/{album_id}")
async def get_album(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    service = AlbumService(db)
    album = await service.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(album)


@router.patch("/{album_id}")
async def update_album(album_id: str, payload: UpdateAlbumPayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    service = AlbumService(db)
    updated = await service.update_album(album_id, payload.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(updated, "album updated")


@router.delete("/{album_id}")
async def delete_album(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    service = AlbumService(db)
    deleted = await service.delete_album(album_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(None, "album deleted")


@router.get("/{album_id}/summary")
async def get_album_summary(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """获取相册完整摘要（含照片/章节/页面/导出统计）。"""
    await require_album_access(db, user, album_id)
    service = AlbumService(db)
    summary = await service.get_summary(album_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(summary)


@router.get("/{album_id}/chapters")
async def list_album_chapters(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    service = AlbumService(db)
    chapters = await service.list_album_chapters(album_id)
    if chapters is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(chapters)


@router.get("/{album_id}/pages")
async def list_album_pages(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    service = AlbumService(db)
    pages = await service.list_album_pages(album_id)
    if pages is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(pages)


@router.get("/{album_id}/tasks")
async def list_album_tasks(
    album_id: str,
    task_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    tasks = await TaskService(db).list_tasks(album_id=album_id, task_type=task_type)
    return success_response(tasks)


@router.get("/{album_id}/tasks/{task_id}")
async def get_album_task(album_id: str, task_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    task = await TaskService(db).get_task(task_id)
    if task is None or task["album_id"] != album_id:
        raise HTTPException(status_code=404, detail="task not found")
    return success_response(task)


@router.post("/{album_id}/tasks/{task_id}/cancel")
async def cancel_album_task(album_id: str, task_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    task = await TaskService(db).get_task(task_id)
    if task is None or task["album_id"] != album_id:
        raise HTTPException(status_code=404, detail="task not found")
    updated = await TaskService(db).request_cancel(task_id)
    return success_response(updated, "task cancel requested")


@router.get("/{album_id}/exports")
async def list_album_exports(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    service = AlbumService(db)
    exports = await service.list_album_exports(album_id)
    if exports is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(exports)
