from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

from PIL import Image


def _build_valid_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), color=(240, 240, 240))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


VALID_JPEG_BYTES = _build_valid_jpeg_bytes()

from app.db import session as db_session
from app.jobs.handlers import (
    run_cleaning_job,
    run_cluster_chapters_job,
    run_export_job,
    run_plan_pages_job,
    run_render_layout_job,
)
from app.services.auth_service import AuthService


def create_auth_headers(client, username: str = "tester", password: str = "secret", role: str = "user") -> dict[str, str]:
    if role == "admin":
        asyncio.run(_ensure_admin_user(username, password))
    else:
        register = client.post("/api/v1/auth/register", json={"username": username, "password": password})
        assert register.status_code == 200
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _ensure_admin_user(username: str, password: str) -> None:
    async with db_session.AsyncSessionFactory() as session:
        await AuthService(session).create_admin_user(username, password)


def create_album(client, headers: dict[str, str], name: str = "测试相册") -> dict:
    response = client.post(
        "/api/v1/albums",
        json={
            "name": name,
            "album_type": "yearbook",
            "book_size": "square_10inch",
            "theme_style": "minimal",
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["data"]


def upload_photo(client, headers: dict[str, str], album_id: str, filename: str, content: bytes = VALID_JPEG_BYTES) -> dict:
    response = client.post(
        f"/api/v1/albums/{album_id}/photos/upload",
        files=[("files", (filename, content, "image/jpeg"))],
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["uploaded"]
    return payload["uploaded"][0]


def run_task_worker(task: dict) -> None:
    task_type = task["task_type"]
    params = task.get("task_params") or {}
    if task_type == "clean_photos":
        asyncio.run(
            run_cleaning_job(
                {},
                task["id"],
                task["album_id"],
                pipeline_version=params.get("pipeline_version"),
            )
        )
        return
    if task_type == "cluster_chapters":
        asyncio.run(run_cluster_chapters_job({}, task["id"], task["album_id"]))
        return
    if task_type == "plan_pages":
        asyncio.run(run_plan_pages_job({}, task["id"], task["album_id"]))
        return
    if task_type == "render_layout":
        asyncio.run(run_render_layout_job({}, task["id"], task["album_id"]))
        return
    if task_type.startswith("export_"):
        asyncio.run(
            run_export_job(
                {},
                task["id"],
                task["album_id"],
                format=params.get("format", task_type.removeprefix("export_")),
            )
        )
        return
    raise AssertionError(f"Unsupported task type: {task_type}")
