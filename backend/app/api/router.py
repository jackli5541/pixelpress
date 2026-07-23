from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_admin
from app.auth.ownership import require_album_access
from app.common.responses import success_response
from app.db.session import get_db
from app.modules.album.api import router as album_router
from app.modules.admin.api import router as admin_router
from app.modules.chapter.api import router as chapter_router
from app.modules.cleaning.api import router as cleaning_router
from app.modules.export.api import router as export_router
from app.modules.layout.api import catalog_router as layout_catalog_router, router as layout_router
from app.modules.photo.api import router as photo_router
from app.modules.theme.api import router as theme_router
from app.modules.user.api import auth_router, users_router
from app.services.layout_service import LayoutService
from app.services.photo_service import PhotoService
from app.services.render_access_service import RenderAccessService
from app.services.task_service import TaskService
from app.storage.file_store import get_file_storage

api_router = APIRouter(prefix="/api/v1")


@api_router.get("/health", tags=["system"])
def health_check() -> dict:
    return success_response({"status": "ok"})


# ── Tasks ──────────────────────────────────────────────

@api_router.get("/tasks", tags=["tasks"])
async def list_tasks(
    album_id: str | None = None,
    task_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_admin),
) -> dict:
    return success_response(await TaskService(db).list_tasks(album_id, task_type))


@api_router.get("/tasks/{task_id}", tags=["tasks"])
async def get_task(task_id: str, db: AsyncSession = Depends(get_db), user=Depends(require_admin)) -> dict:
    task = await TaskService(db).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return success_response(task)


# ── Preview (rendered HTML) ────────────────────────────

@api_router.get("/albums/{album_id}/preview", tags=["preview"])
async def preview_album_html(
    album_id: str,
    style_key: str | None = Query(default=None),
    sample: bool = Query(default=False),
    spread_id: str | None = Query(default=None),
    recipe_key: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """获取已渲染的完整相册 HTML（用于前端预览或浏览器打开）。"""
    album = await require_album_access(db, user, album_id)

    layout_service = LayoutService(db)
    html = (
        await layout_service.build_style_sample(album_id, style_key, spread_id=spread_id, recipe_key=recipe_key)
        if sample and style_key
        else await layout_service.load_preview_html(album_id)
    )
    if not html:
        raise HTTPException(status_code=400, detail="not rendered yet. Please run POST /render first.")

    return success_response({
        "album_id": album_id,
        "html": html,
        "render_revision": album.render_revision,
    })


@api_router.get("/render-assets/albums/{album_id}/photos/{photo_id}", tags=["preview"])
async def preview_render_photo_asset(
    album_id: str,
    photo_id: str,
    token: str = Query(..., min_length=1),
    exp: int = Query(..., gt=0),
    rev: int = Query(..., ge=0),
    db: AsyncSession = Depends(get_db),
) -> Response:
    album = await LayoutService(db).album_repo.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")
    RenderAccessService().verify_photo_preview_token(
        album_id=album_id,
        photo_id=photo_id,
        render_revision=rev,
        token=token,
        exp=exp,
    )
    if album.render_revision != rev:
        raise HTTPException(status_code=403, detail="preview token expired")
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


# ── Register module routers ────────────────────────────

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(admin_router)
api_router.include_router(album_router)
api_router.include_router(photo_router)
api_router.include_router(cleaning_router)
api_router.include_router(theme_router)
api_router.include_router(chapter_router)
api_router.include_router(layout_router)
api_router.include_router(layout_catalog_router)
api_router.include_router(export_router)
