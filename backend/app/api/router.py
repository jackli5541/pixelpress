from fastapi import APIRouter, HTTPException

from app.common.responses import success_response
from app.modules.album.api import router as album_router
from app.modules.chapter.api import router as chapter_router
from app.modules.cleaning.api import router as cleaning_router
from app.modules.export.api import router as export_router
from app.modules.layout.api import router as layout_router
from app.modules.photo.api import router as photo_router
from app.modules.user.api import router as user_router
from app.storage.memory_store import memory_store

api_router = APIRouter(prefix="/api/v1")


@api_router.get("/health", tags=["system"])
def health_check() -> dict:
    return success_response({"status": "ok"})


# ── Tasks ──────────────────────────────────────────────

@api_router.get("/tasks", tags=["tasks"])
def list_tasks(album_id: str | None = None) -> dict:
    return success_response(memory_store.list_tasks(album_id))


@api_router.get("/tasks/{task_id}", tags=["tasks"])
def get_task(task_id: str) -> dict:
    task = memory_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return success_response(task)


# ── Preview (rendered HTML) ────────────────────────────

@api_router.get("/albums/{album_id}/preview", tags=["preview"])
def preview_album_html(album_id: str) -> dict:
    """获取已渲染的完整相册 HTML（用于前端预览或浏览器打开）。"""
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")

    full_html = album.get("full_html", "")
    if not full_html:
        raise HTTPException(status_code=400, detail="not rendered yet. Please run POST /render first.")

    return success_response({
        "album_id": album_id,
        "html": full_html,
    })


# ── Register module routers ────────────────────────────

api_router.include_router(user_router)
api_router.include_router(album_router)
api_router.include_router(photo_router)
api_router.include_router(cleaning_router)
api_router.include_router(chapter_router)
api_router.include_router(layout_router)
api_router.include_router(export_router)
