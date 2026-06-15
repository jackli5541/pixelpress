from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.common.enums import AlbumStatus, TaskStatus
from app.common.responses import success_response
from app.engines.chapter_engine.service import cluster_photos
from app.storage.memory_store import memory_store

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

@router.post("/cluster")
def cluster_chapters(album_id: str) -> dict:
    """启动章节聚类：按时间对照片分组，自动生成章节结构。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    task = memory_store.create_task(album_id, "cluster_chapters")
    memory_store.update_task(task["id"], {"task_status": TaskStatus.RUNNING})

    try:
        # 只对建议保留的照片进行聚类（已标记移除的不参与）
        photos = memory_store.list_photos(album_id)
        keep_photos = [p for p in photos if p.get("cleaning_recommendation") != "remove"]
        if not keep_photos:
            memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})
            memory_store.update_album(album_id, {"status": AlbumStatus.CLUSTERED})
            return success_response({"task": task, "chapters": []}, "clustering complete (no photos)")

        chapter_list = cluster_photos(keep_photos, strategy="time_based")
        memory_store.chapters[album_id] = {}

        created = []
        for ch in chapter_list:
            record = memory_store.create_chapter(album_id, {
                "name": ch["name"],
                "photo_ids": ch["photo_ids"],
                "description": ch.get("time_range", ""),
            })
            created.append(record)

        memory_store.update_album(album_id, {"status": AlbumStatus.CLUSTERED})
        memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})

        return success_response({"task": memory_store.get_task(task["id"]), "chapters": created}, "clustering complete")

    except Exception as exc:
        memory_store.update_task(task["id"], {"task_status": TaskStatus.FAILED})
        raise HTTPException(status_code=500, detail=f"clustering failed: {exc}")


# ── Manual CRUD ────────────────────────────────────────

@router.post("/chapters")
def create_chapter(album_id: str, payload: CreateChapterPayload) -> dict:
    """手动创建章节。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    chapter = memory_store.create_chapter(album_id, {
        "name": payload.name,
        "description": payload.description,
        "photo_ids": payload.photo_ids,
    })
    return success_response(chapter, "chapter created")


@router.patch("/chapters/{chapter_id}")
def update_chapter(album_id: str, chapter_id: str, payload: UpdateChapterPayload) -> dict:
    """更新章节（名称、描述、照片列表）。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    chapter = memory_store.chapters.get(album_id, {}).get(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="chapter not found")

    updates = payload.model_dump(exclude_none=True)
    updated = memory_store.update_chapter(album_id, chapter_id, updates)
    return success_response(updated, "chapter updated")


@router.delete("/chapters/{chapter_id}")
def delete_chapter(album_id: str, chapter_id: str) -> dict:
    """删除章节。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    chapter = memory_store.chapters.get(album_id, {}).pop(chapter_id, None)
    if chapter is None:
        raise HTTPException(status_code=404, detail="chapter not found")

    return success_response(None, "chapter deleted")


@router.post("/chapters/move-photos")
def move_photos_between_chapters(album_id: str, payload: MovePhotosPayload) -> dict:
    """将照片从一个章节移动到另一个章节。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    target = memory_store.chapters.get(album_id, {}).get(payload.target_chapter_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target chapter not found")

    # 从所有章节中移除这些照片
    for ch in memory_store.chapters.get(album_id, {}).values():
        if ch["id"] != payload.target_chapter_id:
            ch["photo_ids"] = [pid for pid in ch.get("photo_ids", []) if pid not in payload.photo_ids]

    # 添加到目标章节（去重）
    existing_ids = set(target.get("photo_ids", []))
    for pid in payload.photo_ids:
        if pid not in existing_ids:
            target["photo_ids"].append(pid)

    return success_response({
        "target_chapter": target,
        "moved_count": len(payload.photo_ids),
    }, "photos moved")


@router.post("/chapters/merge")
def merge_chapters(album_id: str, source_ids: list[str], target_id: str) -> dict:
    """合并章节：将 source 章节的照片合并到 target 章节，删除 source 章节。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    album_chapters = memory_store.chapters.get(album_id, {})
    target = album_chapters.get(target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target chapter not found")

    merged_count = 0
    for sid in source_ids:
        src = album_chapters.get(sid)
        if src and src["id"] != target_id:
            existing = set(target.get("photo_ids", []))
            for pid in src.get("photo_ids", []):
                if pid not in existing:
                    target["photo_ids"].append(pid)
                    existing.add(pid)
                    merged_count += 1
            del album_chapters[sid]

    return success_response({"chapter": target, "merged_photos": merged_count}, "chapters merged")
