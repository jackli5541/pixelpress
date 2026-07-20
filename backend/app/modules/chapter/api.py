from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi.util import get_remote_address

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.auth.ownership import require_album_access
from app.common.responses import success_response
from app.db.session import get_db
from app.services.chapter_service import ChapterService, PendingPhotoReviewError
from app.services.task_service import TaskConflictError

router = APIRouter(prefix="/albums/{album_id}", tags=["chapters"])


class CreateChapterPayload(BaseModel):
    name: str = "新章节"
    description: str = ""
    photo_ids: list[str] = []


class UpdateChapterPayload(BaseModel):
    name: str | None = None
    description: str | None = None
    photo_ids: list[str] | None = None


class MovePhotosPayload(BaseModel):
    photo_ids: list[str]
    target_chapter_id: str


# ── Auto clustering ────────────────────────────────────

@router.post("/cluster", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(lambda: get_settings().rate_limit_task_trigger, key_func=get_remote_address)
async def cluster_chapters(request: Request, album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """启动章节聚类：按时间对照片分组，自动生成章节结构。"""
    await require_album_access(db, user, album_id)
    try:
        task = await ChapterService(db).request_cluster_chapters(album_id, user.id)
    except PendingPhotoReviewError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "pending photo review", "pending_review_count": exc.pending_review_count},
        ) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": "active task exists", "task": exc.task}) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response({"task": task, "status_url": f"/api/v1/albums/{album_id}/tasks/{task['id']}"}, "clustering queued")


# ── Manual CRUD ────────────────────────────────────────

@router.post("/chapters")
async def create_chapter(album_id: str, payload: CreateChapterPayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """手动创建章节。"""
    await require_album_access(db, user, album_id)
    chapter = await ChapterService(db).create_chapter(album_id, payload.model_dump())
    if chapter is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(chapter, "chapter created")


@router.patch("/chapters/{chapter_id}")
async def update_chapter(album_id: str, chapter_id: str, payload: UpdateChapterPayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """更新章节（名称、描述、照片列表）。"""
    await require_album_access(db, user, album_id)
    updated, error = await ChapterService(db).update_chapter(album_id, chapter_id, payload.model_dump(exclude_none=True))
    if error == "album":
        raise HTTPException(status_code=404, detail="album not found")
    if error == "chapter":
        raise HTTPException(status_code=404, detail="chapter not found")
    return success_response(updated, "chapter updated")


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(album_id: str, chapter_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """删除章节。"""
    await require_album_access(db, user, album_id)
    error = await ChapterService(db).delete_chapter(album_id, chapter_id)
    if error == "album":
        raise HTTPException(status_code=404, detail="album not found")
    if error == "chapter":
        raise HTTPException(status_code=404, detail="chapter not found")
    return success_response(None, "chapter deleted")


@router.post("/chapters/move-photos")
async def move_photos_between_chapters(album_id: str, payload: MovePhotosPayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """将照片从一个章节移动到另一个章节。"""
    await require_album_access(db, user, album_id)
    result, error = await ChapterService(db).move_photos(album_id, payload.photo_ids, payload.target_chapter_id)
    if error == "album":
        raise HTTPException(status_code=404, detail="album not found")
    if error == "target":
        raise HTTPException(status_code=404, detail="target chapter not found")
    return success_response(result, "photos moved")


@router.post("/chapters/merge")
async def merge_chapters(album_id: str, source_ids: list[str], target_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """合并章节：将 source 章节的照片合并到 target 章节，删除 source 章节。"""
    await require_album_access(db, user, album_id)
    result, error = await ChapterService(db).merge_chapters(album_id, source_ids, target_id)
    if error == "album":
        raise HTTPException(status_code=404, detail="album not found")
    if error == "target":
        raise HTTPException(status_code=404, detail="target chapter not found")
    return success_response(result, "chapters merged")
