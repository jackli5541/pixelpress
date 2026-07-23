import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from slowapi.util import get_remote_address

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.auth.ownership import require_album_access, require_export_access
from app.common.responses import success_response
from app.db.session import get_db
from app.services.export_service import ExportService
from app.services.task_service import TaskConflictError

router = APIRouter(prefix="/albums/{album_id}/export", tags=["export"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(lambda: get_settings().rate_limit_export, key_func=get_remote_address)
async def export_endpoint(
    request: Request,
    album_id: str,
    format: str = Query("html", description="导出格式: html 或 pdf"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    """导出相册为 HTML 或 PDF 文件。"""
    await require_album_access(db, user, album_id)
    try:
        task = await ExportService(db).request_export_album(album_id, user.id, format)
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail={"message": "active task exists", "task": exc.task}) from exc
    if task is not None and task.get("cache_hit"):
        return success_response(task, "export cache hit")
    if task is None:
        raise HTTPException(status_code=400, detail="请先执行排版渲染后再导出。")
    return success_response({"task": task, "status_url": f"/api/v1/albums/{album_id}/tasks/{task['id']}"}, "导出任务已提交")


@router.get("/download/{export_id}")
async def download_export(
    album_id: str,
    export_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
) -> FileResponse:
    """下载已导出的文件。"""
    export = await require_export_access(db, user, album_id, export_id)
    try:
        result = await ExportService(db).open_export_content(album_id, export_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="export file not found") from None
    except Exception:
        raise HTTPException(status_code=502, detail="export file unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="导出文件不存在")

    export_record, content = result
    fmt = export_record.format or "html"
    media_type = "application/pdf" if fmt == "pdf" else "text/html"
    source_name = Path(export_record.file_path or f"{export_id}.{fmt}").name
    suffix = Path(source_name).suffix or (".pdf" if fmt == "pdf" else ".html")

    with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        temp_path = temp_file.name

    def _cleanup_temp_file() -> None:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return FileResponse(
        path=temp_path,
        filename=source_name,
        media_type=media_type,
        background=BackgroundTask(_cleanup_temp_file),
    )
