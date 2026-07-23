from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi.util import get_remote_address

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.auth.ownership import require_album_access
from app.common.responses import success_response
from app.db.session import get_db
from app.services.layout_service import LayoutService
from app.services.task_service import TaskConflictError

router = APIRouter(prefix="/albums/{album_id}", tags=["layout"])
catalog_router = APIRouter(prefix="/layout", tags=["layout"])


class CreatePagePayload(BaseModel):
    chapter_id: str | None = None
    template: str = "grid_3"
    photo_ids: list[str] = []
    meta: dict | None = None


class UpdatePagePayload(BaseModel):
    page_number: int | None = None
    template: str | None = None
    photo_ids: list[str] | None = None
    meta: dict | None = None


class MovePagePhotosPayload(BaseModel):
    photo_ids: list[str]
    target_page_id: str


class SpreadPhotoSlotPayload(BaseModel):
    photo_id: str
    focal_x: float = Field(default=0.5, ge=0.0, le=1.0)
    focal_y: float = Field(default=0.5, ge=0.0, le=1.0)


class UpdateSpreadPayload(BaseModel):
    recipe_key: str | None = None
    headline: str | None = Field(default=None, max_length=18)
    body: str | None = Field(default=None, max_length=70)
    needs_review: bool | None = None
    photo_slots: list[SpreadPhotoSlotPayload] = Field(default_factory=list)


@catalog_router.get("/catalog")
async def get_layout_catalog(user=Depends(get_current_user)) -> dict:
    return success_response(LayoutService.get_layout_catalog())


# ── Auto planning ──────────────────────────────────────

@router.post("/plan", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(lambda: get_settings().rate_limit_task_trigger, key_func=get_remote_address)
async def plan_pages_endpoint(
    request: Request,
    album_id: str,
    layout_version: str | None = Query(default=None, pattern="^(legacy_page_v1|spread_v2)$"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """启动页面规划：将照片分配到各页，自动选择版式模板。"""
    await require_album_access(db, user, album_id)
    try:
        task = await LayoutService(db).request_plan_pages(album_id, user.id, layout_version)
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": "active task exists", "task": exc.task}) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response({"task": task, "status_url": f"/api/v1/albums/{album_id}/tasks/{task['id']}"}, "page planning queued")


@router.get("/spreads")
async def list_spreads(album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    await require_album_access(db, user, album_id)
    spreads = await LayoutService(db).list_spreads(album_id)
    if spreads is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(spreads)


@router.patch("/spreads/{spread_id}")
async def update_spread(
    album_id: str,
    spread_id: str,
    payload: UpdateSpreadPayload,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    updated, error = await LayoutService(db).update_spread(album_id, spread_id, payload.model_dump(exclude_none=True))
    if error == "album":
        raise HTTPException(status_code=404, detail="album not found")
    if error == "spread":
        raise HTTPException(status_code=404, detail="spread not found")
    if error == "recipe":
        raise HTTPException(status_code=422, detail="recipe must be one of this spread's compatible candidates")
    return success_response(updated, "spread updated")


@router.post("/spreads/{spread_id}/regenerate-copy")
async def regenerate_spread_copy(
    album_id: str,
    spread_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    await require_album_access(db, user, album_id)
    updated = await LayoutService(db).regenerate_spread_copy(album_id, spread_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="spread not found")
    return success_response(updated, "spread copy regenerated")


# ── Manual Page CRUD ───────────────────────────────────

@router.post("/pages")
async def create_page(album_id: str, payload: CreatePagePayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """手动创建页面。"""
    await require_album_access(db, user, album_id)
    page = await LayoutService(db).create_page(album_id, payload.model_dump())
    if page is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response(page, "page created")


@router.patch("/pages/{page_id}")
async def update_page(album_id: str, page_id: str, payload: UpdatePagePayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """更新页面（页码、模板、照片列表）。"""
    await require_album_access(db, user, album_id)
    updated, error = await LayoutService(db).update_page(album_id, page_id, payload.model_dump(exclude_none=True))
    if error == "album":
        raise HTTPException(status_code=404, detail="album not found")
    if error == "page":
        raise HTTPException(status_code=404, detail="page not found")
    return success_response(updated, "page updated")


@router.delete("/pages/{page_id}")
async def delete_page(album_id: str, page_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """删除页面。"""
    await require_album_access(db, user, album_id)
    error = await LayoutService(db).delete_page(album_id, page_id)
    if error == "album":
        raise HTTPException(status_code=404, detail="album not found")
    if error == "page":
        raise HTTPException(status_code=404, detail="page not found")
    return success_response(None, "page deleted")


@router.post("/pages/move-photos")
async def move_photos_between_pages(album_id: str, payload: MovePagePhotosPayload, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """将照片从一个页面移动到另一个页面。"""
    await require_album_access(db, user, album_id)
    result, error = await LayoutService(db).move_photos(album_id, payload.photo_ids, payload.target_page_id)
    if error == "album":
        raise HTTPException(status_code=404, detail="album not found")
    if error == "target":
        raise HTTPException(status_code=404, detail="target page not found")
    return success_response(result, "photos moved")


# ── Render ─────────────────────────────────────────────

@router.post("/render", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(lambda: get_settings().rate_limit_task_trigger, key_func=get_remote_address)
async def render_layout(request: Request, album_id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)) -> dict:
    """执行排版渲染：对所有已规划的页面生成 HTML 预览。"""
    await require_album_access(db, user, album_id)
    try:
        task = await LayoutService(db).request_render_layout(album_id, user.id)
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": "active task exists", "task": exc.task}) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="album not found")
    return success_response({"task": task, "status_url": f"/api/v1/albums/{album_id}/tasks/{task['id']}"}, "render queued")
