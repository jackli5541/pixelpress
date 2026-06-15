import os
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.common.enums import AlbumStatus, TaskStatus
from app.common.responses import success_response
from app.engines.export_engine.service import export_to_pdf, EXPORTS_DIR
from app.storage.memory_store import memory_store

router = APIRouter(prefix="/albums/{album_id}/export", tags=["export"])


def _save_html_export(album: dict, export_id: str) -> dict:
    """保存 HTML 文件到磁盘。"""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = album.get("name", "album").replace(" ", "_")[:40]
    html_path = EXPORTS_DIR / f"{safe_name}_{export_id[:8]}.html"
    html_path.write_text(album.get("full_html", ""), encoding="utf-8")
    return {
        "format": "html",
        "file_path": str(html_path),
        "file_size": html_path.stat().st_size,
    }


@router.post("")
def export_endpoint(
    album_id: str,
    format: str = Query("html", description="导出格式: html 或 pdf"),
) -> dict:
    """导出相册为 HTML 或 PDF 文件。

    - format=html: 直接保存渲染好的 HTML（即时、无需额外依赖）
    - format=pdf:  使用 Playwright 将 HTML 转为 PDF（需安装 playwright）
    """
    album = memory_store.get_album(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="album not found")

    if album.get("status") != AlbumStatus.RENDERED:
        raise HTTPException(
            status_code=400,
            detail=f"请先执行排版渲染（当前状态: {album['status']}）",
        )

    full_html = album.get("full_html", "")
    if not full_html:
        raise HTTPException(status_code=400, detail="没有可导出的内容，请先执行排版渲染。")

    task = memory_store.create_task(album_id, f"export_{format}")
    memory_store.update_task(task["id"], {"task_status": TaskStatus.RUNNING})

    try:
        export_id = str(uuid4())

        if format == "pdf":
            page_size = album.get("book_size", "A4")
            result = export_to_pdf(
                html_content=full_html,
                album_name=album.get("name", "相册"),
                export_id=export_id,
                page_size=page_size,
            )
            if result["format"] == "html":
                # Playwright 不可用，降级
                fmt_label = "HTML (PDF 引擎未安装)"
            else:
                fmt_label = "PDF"
        else:
            result = _save_html_export(album, export_id)
            fmt_label = "HTML"

        export_record = memory_store.create_export(album_id, {
            "status": "completed",
            "file_path": result["file_path"],
            "file_size": result["file_size"],
            "format": result["format"],
            "task_id": task["id"],
        })

        memory_store.update_album(album_id, {"status": AlbumStatus.EXPORTED})
        memory_store.update_task(task["id"], {"task_status": TaskStatus.SUCCEEDED})

        return success_response(export_record, f"导出成功: {fmt_label}")

    except Exception as exc:
        memory_store.update_task(task["id"], {"task_status": TaskStatus.FAILED})
        raise HTTPException(status_code=500, detail=f"导出失败: {exc}")


@router.get("/download/{export_id}")
def download_export(album_id: str, export_id: str) -> FileResponse:
    """下载已导出的文件。"""
    export = memory_store.exports.get(album_id, {}).get(export_id)
    if export is None:
        raise HTTPException(status_code=404, detail="export not found")

    file_path = export.get("file_path")
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="导出文件不存在")

    fmt = export.get("format", "html")
    media_type = "application/pdf" if fmt == "pdf" else "text/html"
    filename = os.path.basename(file_path)

    return FileResponse(path=file_path, filename=filename, media_type=media_type)
