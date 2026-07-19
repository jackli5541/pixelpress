from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
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


class CleaningDecisionPayload(BaseModel):
    photo_ids: list[str] = Field(min_length=1, max_length=200)
    decision: Literal["keep", "remove"] | None


class CleaningResetPayload(BaseModel):
    clear_user_decisions: bool = False


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(lambda: get_settings().rate_limit_task_trigger, key_func=get_remote_address)
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


@router.get("/results")
async def get_cleaning_results(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    result = await CleaningService(db).get_results(album_id)
    if result is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(result)


@router.patch("/decisions")
async def update_cleaning_decisions(payload: CleaningDecisionPayload, album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    result = await CleaningService(db).apply_decisions(album_id, payload.photo_ids, payload.decision)
    if result is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(result, "cleaning decisions updated")


@router.post("/groups/{group_id}/accept-preferred")
async def accept_group_preferred(group_id: str, album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    result = await CleaningService(db).accept_group_preferred(album_id, group_id)
    if result is None:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    return success_response(result, "preferred photo accepted")


@router.post("/reset")
async def reset_cleaning(album_id: str, payload: CleaningResetPayload | None = None, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """重置清洗结果，将相册回退到 uploaded 状态。"""
    await require_album_access(db, user, album_id)
    album = await CleaningService(db).reset_cleaning(album_id, clear_user_decisions=bool(payload and payload.clear_user_decisions))
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(album, "cleaning reset")
