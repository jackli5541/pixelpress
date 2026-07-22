from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi.util import get_remote_address

from app.auth.dependencies import get_current_user
from app.auth.ownership import require_album_access
from app.common.responses import success_response
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.services.task_service import TaskConflictError
from app.services.theme_curation_service import (
    CHAPTER_STRATEGIES,
    ThemeCurationService,
    ThemeProfileStateError,
    ThemeRebuildConfirmationError,
    ThemeReviewUnresolvedError,
)


router = APIRouter(prefix="/albums/{album_id}", tags=["theme-curation"])


class ThemeAnalysisPayload(BaseModel):
    custom_theme: str | None = Field(default=None, max_length=500)


class ThemeSelectionPayload(BaseModel):
    profile_id: str
    candidate_id: str
    chapter_strategy: str
    confirm_rebuild: bool = False


class ThemeDecisionPayload(BaseModel):
    photo_ids: list[str] = Field(min_length=1)
    decision: str | None = None


class ThemeReviewReopenPayload(BaseModel):
    confirm_rebuild: bool = False


@router.post("/theme-analysis", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(lambda: get_settings().rate_limit_task_trigger, key_func=get_remote_address)
async def analyze_theme(
    request: Request,
    album_id: str,
    payload: ThemeAnalysisPayload | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    try:
        task = await ThemeCurationService(db).request_analysis(
            album_id,
            user.id,
            custom_theme=payload.custom_theme if payload else None,
        )
    except ThemeProfileStateError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": "active task exists", "task": exc.task}) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response({"task": task}, "theme analysis queued")


@router.get("/theme-workspace")
async def get_theme_workspace(
    album_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    workspace = await ThemeCurationService(db).workspace(album_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(workspace)


@router.post("/theme-selection", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(lambda: get_settings().rate_limit_task_trigger, key_func=get_remote_address)
async def select_theme(
    request: Request,
    album_id: str,
    payload: ThemeSelectionPayload,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    if payload.chapter_strategy not in CHAPTER_STRATEGIES:
        raise HTTPException(status_code=422, detail="invalid chapter strategy")
    try:
        task = await ThemeCurationService(db).request_selection(
            album_id,
            user.id,
            profile_id=payload.profile_id,
            candidate_id=payload.candidate_id,
            chapter_strategy=payload.chapter_strategy,
            confirm_rebuild=payload.confirm_rebuild,
        )
    except ThemeRebuildConfirmationError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "theme change requires chapter rebuild confirmation", "chapter_count": exc.chapter_count},
        ) from exc
    except ThemeProfileStateError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": "active task exists", "task": exc.task}) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response({"task": task}, "theme scoring queued")


@router.patch("/theme-review/decisions")
async def update_theme_decisions(
    album_id: str,
    payload: ThemeDecisionPayload,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    try:
        result = await ThemeCurationService(db).update_decisions(album_id, payload.photo_ids, payload.decision)
    except ThemeProfileStateError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
    return success_response(result, "theme decisions updated")


@router.post("/theme-review/reopen")
async def reopen_theme_review(
    album_id: str,
    payload: ThemeReviewReopenPayload | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    try:
        profile = await ThemeCurationService(db).reopen_review(
            album_id,
            confirm_rebuild=payload.confirm_rebuild if payload else False,
        )
    except ThemeRebuildConfirmationError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "theme review requires chapter rebuild confirmation", "chapter_count": exc.chapter_count},
        ) from exc
    except ThemeProfileStateError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(profile, "theme review reopened")


@router.post("/theme-review/confirm")
async def confirm_theme_review(
    album_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    try:
        profile = await ThemeCurationService(db).confirm_review(album_id)
    except ThemeReviewUnresolvedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "theme review is incomplete", "review_count": exc.review_count},
        ) from exc
    except ThemeProfileStateError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(profile, "theme review confirmed")
