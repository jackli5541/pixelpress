from fastapi import APIRouter, HTTPException

from app.common.enums import AlbumStatus, TaskStatus
from app.common.responses import success_response
from app.engines.cleaning_engine.service import run_cleaning
from app.storage.memory_store import memory_store

router = APIRouter(prefix="/albums/{album_id}/clean", tags=["cleaning"])


@router.post("")
def start_cleaning(album_id: str) -> dict:
    """启动照片清洗：对相册中所有照片进行质量分析。"""
    if memory_store.get_album(album_id) is None:
        raise HTTPException(status_code=404, detail="album not found")

    task = memory_store.create_task(album_id, "clean_photos")
    memory_store.update_task(task["id"], {"task_status": TaskStatus.RUNNING})

    try:
        photos = memory_store.list_photos(album_id)
        if not photos:
            memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})
            memory_store.update_album(album_id, {"status": AlbumStatus.CLEANED})
            return success_response(
                {"task": task, "result": {"summary": {"total": 0, "keep": 0, "remove": 0}}},
                "cleaning complete (no photos)",
            )

        # 执行清洗引擎
        result = run_cleaning(album_id, photos)

        # 将清洗结果写回每张照片
        for item in result["per_photo"]:
            memory_store.update_photo(
                album_id,
                item["photo_id"],
                {
                    "quality_score": item["quality_score"],
                    "scene_tags": item["tags"],
                    "cleaning_recommendation": item["recommendation"],
                    "cleaning_issues": item["issues"],
                },
            )

        # 更新相册状态
        memory_store.update_album(album_id, {"status": AlbumStatus.CLEANED})
        memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})

        return success_response(
            {"task": memory_store.get_task(task["id"]), "result": result},
            "cleaning complete",
        )

    except Exception as exc:
        memory_store.update_task(task["id"], {"task_status": TaskStatus.FAILED})
        raise HTTPException(status_code=500, detail=f"cleaning failed: {exc}")


@router.post("/reset")
def reset_cleaning(album_id: str) -> dict:
    """重置清洗结果，将相册回退到 uploaded 状态。"""
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")

    # 清除清洗相关字段
    for photo in memory_store.list_photos(album_id):
        memory_store.update_photo(
            album_id,
            photo["id"],
            {
                "quality_score": None,
                "scene_tags": None,
                "cleaning_recommendation": None,
                "cleaning_issues": None,
            },
        )

    memory_store.update_album(album_id, {"status": AlbumStatus.UPLOADED})
    return success_response(album, "cleaning reset")
