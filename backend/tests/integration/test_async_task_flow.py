from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db import session as db_session
from app.jobs import enqueue as enqueue_module
from app.models.album import Album
from app.models.task import Task
from app.services.task_dispatch_service import TaskDispatchService
from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


async def _flush_dispatches() -> int:
    async with db_session.AsyncSessionFactory() as session:
        return await TaskDispatchService(session).flush_pending_dispatches()


async def _get_dispatch_status(task_id: str) -> str:
    async with db_session.AsyncSessionFactory() as session:
        result = await session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.dispatches))
        )
        db_task = result.scalar_one()
        return db_task.dispatches[0].dispatch_status


async def _clear_dispatch_backoff(task_id: str) -> None:
    async with db_session.AsyncSessionFactory() as session:
        result = await session.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.dispatches))
        )
        db_task = result.scalar_one()
        dispatch = db_task.dispatches[0]
        dispatch.available_at = None
        await session.commit()


async def _get_album_model(album_id: str) -> Album:
    async with db_session.AsyncSessionFactory() as session:
        result = await session.execute(select(Album).where(Album.id == album_id))
        return result.scalar_one()


def test_clean_enqueue_returns_queued_task_and_worker_completes(client):
    headers = create_auth_headers(client, username="async-owner", password="secret", role="user")
    album = create_album(client, headers, name="Async Clean Album")
    upload_photo(client, headers, album["id"], "a.jpg")

    response = client.post(f"/api/v1/albums/{album['id']}/clean", headers=headers)
    assert response.status_code == 202
    task = response.json()["data"]["task"]
    assert task["task_status"] == "queued"
    assert task["progress_step"] == "queued"

    run_task_worker(task)

    detail = client.get(f"/api/v1/albums/{album['id']}/tasks/{task['id']}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()["data"]
    assert payload["task_status"] == "succeeded"
    assert payload["progress_pct"] == 100
    assert payload["result_payload"]["summary"]["total"] == 1


def test_conflicting_active_task_returns_409(client):
    headers = create_auth_headers(client, username="conflict-owner", password="secret", role="user")
    album = create_album(client, headers, name="Conflict Album")

    first = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert first.status_code == 202
    second = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert second.status_code == 409


def test_cancel_album_task_marks_queued_task_cancelled(client):
    headers = create_auth_headers(client, username="cancel-owner", password="secret", role="user")
    album = create_album(client, headers, name="Cancel Album")

    queued = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert queued.status_code == 202
    task = queued.json()["data"]["task"]

    cancel = client.post(f"/api/v1/albums/{album['id']}/tasks/{task['id']}/cancel", headers=headers)
    assert cancel.status_code == 200
    updated = cancel.json()["data"]
    assert updated["cancel_requested"] is True
    assert updated["task_status"] == "cancelled"


def test_dispatch_flush_recovers_pending_dispatch(client, monkeypatch):
    headers = create_auth_headers(client, username="dispatch-owner", password="secret", role="user")
    album = create_album(client, headers, name="Dispatch Album")

    original_enqueue = enqueue_module.enqueue_job

    async def broken_enqueue(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(enqueue_module, "enqueue_job", broken_enqueue)
    response = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert response.status_code == 202
    task = response.json()["data"]["task"]
    assert asyncio.run(_get_dispatch_status(task["id"])) == "pending"

    monkeypatch.setattr(enqueue_module, "enqueue_job", original_enqueue)
    asyncio.run(_clear_dispatch_backoff(task["id"]))
    flushed = asyncio.run(_flush_dispatches())
    assert flushed >= 1
    assert asyncio.run(_get_dispatch_status(task["id"])) == "dispatched"


def test_render_preview_and_export_follow_async_pipeline(client):
    settings = get_settings()
    headers = create_auth_headers(client, username="async-admin", password="secret", role="admin")
    album = create_album(client, headers, name="Async Preview Export")
    p1 = upload_photo(client, headers, album["id"], "a.jpg")
    p2 = upload_photo(client, headers, album["id"], "b.jpg")
    p3 = upload_photo(client, headers, album["id"], "c.jpg")

    chapter_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "章节A", "description": "desc", "photo_ids": [p1["id"], p2["id"], p3["id"]]},
        headers=headers,
    )
    assert chapter_response.status_code == 200

    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 202
    run_task_worker(plan_response.json()["data"]["task"])

    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 202
    run_task_worker(render_response.json()["data"]["task"])

    preview_response = client.get(f"/api/v1/albums/{album['id']}/preview", headers=headers)
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["album_id"] == album["id"]
    assert preview_payload["render_revision"] == 1
    assert "章节A" in preview_payload["html"]
    assert "/api/v1/render-assets/albums/" in preview_payload["html"]
    assert "data:image/jpeg;base64," not in preview_payload["html"]

    album_model = asyncio.run(_get_album_model(album["id"]))
    assert album_model.full_html is None
    assert album_model.preview_html_path == f"albums/{album['id']}/artifacts/r1/preview.html"
    assert album_model.print_html_path == f"albums/{album['id']}/artifacts/r1/print.html"
    assert album_model.render_manifest_path == f"albums/{album['id']}/artifacts/r1/manifest.json"
    assert (Path(settings.uploads_dir) / album_model.preview_html_path).exists()
    assert (Path(settings.uploads_dir) / album_model.print_html_path).exists()
    assert (Path(settings.uploads_dir) / album_model.render_manifest_path).exists()

    export_response = client.post(f"/api/v1/albums/{album['id']}/export", headers=headers)
    assert export_response.status_code == 202
    export_task = export_response.json()["data"]["task"]
    run_task_worker(export_task)

    exports_response = client.get(f"/api/v1/albums/{album['id']}/exports", headers=headers)
    assert exports_response.status_code == 200
    exports = exports_response.json()["data"]
    assert len(exports) == 1
    export_record = exports[0]
    assert export_record["task_id"] == export_task["id"]

    download_response = client.get(
        f"/api/v1/albums/{album['id']}/export/download/{export_record['id']}",
        headers=headers,
    )
    assert download_response.status_code == 200
    assert download_response.content
    assert b"data:image/jpeg;base64," in download_response.content

    export_storage_path = Path(settings.uploads_dir) / export_record["file_path"]
    assert export_storage_path.exists()


def test_pdf_export_failure_marks_task_failed(client, monkeypatch):
    headers = create_auth_headers(client, username="pdf-fail-admin", password="secret", role="admin")
    album = create_album(client, headers, name="PDF Failure Album")
    p1 = upload_photo(client, headers, album["id"], "a.jpg")

    chapter_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "PDF Chapter", "description": "desc", "photo_ids": [p1["id"]]},
        headers=headers,
    )
    assert chapter_response.status_code == 200

    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 202
    run_task_worker(plan_response.json()["data"]["task"])

    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 202
    run_task_worker(render_response.json()["data"]["task"])

    from app.engines.export_engine.service import PdfExportError
    from app.services import export_service as export_service_module

    async def fake_export_to_pdf(*args, **kwargs):  # noqa: ANN002, ANN003
        raise PdfExportError("playwright broken")

    monkeypatch.setattr(export_service_module, "export_to_pdf", fake_export_to_pdf)

    export_response = client.post(f"/api/v1/albums/{album['id']}/export?format=pdf", headers=headers)
    assert export_response.status_code == 202
    export_task = export_response.json()["data"]["task"]
    run_task_worker(export_task)

    detail = client.get(f"/api/v1/albums/{album['id']}/tasks/{export_task['id']}", headers=headers)
    assert detail.status_code == 200
    payload = detail.json()["data"]
    assert payload["task_status"] == "failed"
    assert payload["error_code"] == "pdf_export_failed"
    assert payload["debug_payload"]["format"] == "pdf"
    assert payload["debug_payload"]["stage"] == "pdf_generate"
    assert "playwright broken" in payload["debug_payload"]["reason"]

    exports_response = client.get(f"/api/v1/albums/{album['id']}/exports", headers=headers)
    assert exports_response.status_code == 200
    assert exports_response.json()["data"] == []

    album_detail = client.get(f"/api/v1/albums/{album['id']}", headers=headers)
    assert album_detail.status_code == 200
    assert album_detail.json()["data"]["status"] == "rendered"
