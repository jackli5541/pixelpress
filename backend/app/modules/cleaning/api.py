from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi.util import get_remote_address

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.auth.ownership import require_album_access
from app.common.responses import success_response
from app.db.session import get_db
from app.services.cleaning_service import CleaningService
from app.services.task_service import TaskConflictError

router = APIRouter(prefix="/albums/{album_id}/clean", tags=["cleaning"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().rate_limit_task_trigger, key_func=get_remote_address)
async def start_cleaning(request: Request, album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """启动照片清洗：对相册中所有照片进行质量分析。"""
    await require_album_access(db, user, album_id)
    try:
        task = await CleaningService(db).request_cleaning(album_id, user.id)
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": "active task exists", "task": exc.task}) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response({"task": task, "status_url": f"/api/v1/albums/{album_id}/tasks/{task['id']}"}, "cleaning queued")


@router.post("/reset")
async def reset_cleaning(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """重置清洗结果，将相册回退到 uploaded 状态。"""
    await require_album_access(db, user, album_id)
    album = await CleaningService(db).reset_cleaning(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(album, "cleaning reset")
