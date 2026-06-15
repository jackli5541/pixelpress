from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.common.enums import AlbumStatus, TaskStatus
from app.common.responses import success_response
from app.engines.layout_engine.service import (
    plan_pages,
    generate_full_html,
    generate_layout_html,
    LAYOUT_TEMPLATES,
)
from app.storage.memory_store import memory_store

router = APIRouter(prefix="/albums/{album_id}", tags=["layout"])


class CreatePagePayload(BaseModel):
    chapter_id: str | None = None
    template: str = "grid_3"
    photo_ids: list[str] = []


class UpdatePagePayload(BaseModel):
    page_number: int | None = None
    template: str | None = None
    photo_ids: list[str] | None = None


class MovePagePhotosPayload(BaseModel):
    photo_ids: list[str]
    target_page_id: str


# ── Auto planning ──────────────────────────────────────

@router.post("/plan")
def plan_pages_endpoint(album_id: str) -> dict:
    """启动页面规划：将照片分配到各页，自动选择版式模板。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    task = memory_store.create_task(album_id, "plan_pages")
    memory_store.update_task(task["id"], {"task_status": TaskStatus.RUNNING})

    try:
        # 只对建议保留的照片进行规划（已标记移除的不参与）
        photos = memory_store.list_photos(album_id)
        keep_photos = [p for p in photos if p.get("cleaning_recommendation") != "remove"]
        if not keep_photos:
            memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})
            memory_store.update_album(album_id, {"status": AlbumStatus.PLANNED})
            return success_response({"task": task, "pages": []}, "page planning complete (no photos)")

        pages_plan = plan_pages(keep_photos, photos_per_page=3)
        memory_store.pages[album_id] = {}

        created = []
        for pp in pages_plan:
            page = memory_store.create_page(album_id, {
                "chapter_id": None,
                "page_number": pp["page_number"],
                "template": pp["template"]["template"],
                "photo_ids": pp["photo_ids"],
                "photo_count": pp["photo_count"],
                "html": "",
            })
            created.append(page)

        memory_store.update_album(album_id, {"status": AlbumStatus.PLANNED})
        memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})

        return success_response({"task": memory_store.get_task(task["id"]), "pages": created}, "page planning complete")

    except Exception as exc:
        memory_store.update_task(task["id"], {"task_status": TaskStatus.FAILED})
        raise HTTPException(status_code=500, detail=f"page planning failed: {exc}")


# ── Manual Page CRUD ───────────────────────────────────

@router.post("/pages")
def create_page(album_id: str, payload: CreatePagePayload) -> dict:
    """手动创建页面。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    page = memory_store.create_page(album_id, {
        "chapter_id": payload.chapter_id,
        "template": payload.template,
        "photo_ids": payload.photo_ids,
    })
    return success_response(page, "page created")


@router.patch("/pages/{page_id}")
def update_page(album_id: str, page_id: str, payload: UpdatePagePayload) -> dict:
    """更新页面（页码、模板、照片列表）。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    page = memory_store.pages.get(album_id, {}).get(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")

    updates = payload.model_dump(exclude_none=True)
    if "photo_ids" in updates:
        updates["photo_count"] = len(updates["photo_ids"])
    updated = memory_store.update_page(album_id, page_id, updates)
    return success_response(updated, "page updated")


@router.delete("/pages/{page_id}")
def delete_page(album_id: str, page_id: str) -> dict:
    """删除页面。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    page = memory_store.pages.get(album_id, {}).pop(page_id, None)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")

    # 重新编号
    remaining = sorted(memory_store.pages[album_id].values(), key=lambda p: p.get("page_number", 0))
    for i, p in enumerate(remaining, 1):
        p["page_number"] = i

    return success_response(None, "page deleted")


@router.post("/pages/move-photos")
def move_photos_between_pages(album_id: str, payload: MovePagePhotosPayload) -> dict:
    """将照片从一个页面移动到另一个页面。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    target = memory_store.pages.get(album_id, {}).get(payload.target_page_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target page not found")

    # 从所有页面中移除这些照片
    for pg in memory_store.pages.get(album_id, {}).values():
        if pg["id"] != payload.target_page_id:
            pg["photo_ids"] = [pid for pid in pg.get("photo_ids", []) if pid not in payload.photo_ids]
            pg["photo_count"] = len(pg["photo_ids"])

    # 添加到目标页面
    existing = set(target.get("photo_ids", []))
    for pid in payload.photo_ids:
        if pid not in existing:
            target["photo_ids"].append(pid)
            existing.add(pid)
    target["photo_count"] = len(target["photo_ids"])

    return success_response({"target_page": target, "moved_count": len(payload.photo_ids)}, "photos moved")


# ── Render ─────────────────────────────────────────────

@router.post("/render")
def render_layout(album_id: str) -> dict:
    """执行排版渲染：对所有已规划的页面生成 HTML 预览。"""
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")

    task = memory_store.create_task(album_id, "render_layout")
    memory_store.update_task(task["id"], {"task_status": TaskStatus.RUNNING})

    try:
        pages = memory_store.list_pages(album_id)
        if not pages:
            memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})
            memory_store.update_album(album_id, {"status": AlbumStatus.RENDERED})
            return success_response({"task": task, "html": ""}, "render complete (no pages)")

        photos_by_id = {photo["id"]: photo for photo in memory_store.list_photos(album_id)}

        pages_plan = []
        for page in sorted(pages, key=lambda p: p.get("page_number", 0)):
            pages_plan.append({
                "page_number": page["page_number"],
                "photo_ids": page["photo_ids"],
                "template": {"template": page.get("template", "grid_3")},
            })

        full_html = generate_full_html(pages_plan, photos_by_id, album_name=album.get("name", "相册"))

        for page in pages:
            page_photos = [photos_by_id[pid] for pid in page["photo_ids"] if pid in photos_by_id]
            if not page_photos:
                continue
            tmpl = LAYOUT_TEMPLATES.get(page.get("template", "grid_3"), LAYOUT_TEMPLATES["grid_3"])
            template_info = {"template": page.get("template", "grid_3"), "css_class": tmpl["css_class"], "slots": tmpl["slots"]}
            single_html = generate_layout_html(template_info, page_photos, page["page_number"])
            memory_store.update_page(album_id, page["id"], {"html": single_html, "status": "rendered"})

        memory_store.update_album(album_id, {"status": AlbumStatus.RENDERED, "full_html": full_html})
        memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})

        return success_response({"task": memory_store.get_task(task["id"]), "page_count": len(pages)}, "render complete")

    except Exception as exc:
        memory_store.update_task(task["id"], {"task_status": TaskStatus.FAILED})
        raise HTTPException(status_code=500, detail=f"render failed: {exc}")
