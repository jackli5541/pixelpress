from __future__ import annotations

import asyncio
from pathlib import Path

from app.common.enums import TaskStatus
from app.core.config import get_settings
from app.db import session as db_session
from app.models.task import Task
from .helpers import create_album, create_auth_headers, upload_photo


def test_album_list_exposes_resume_fields(client):
    headers = create_auth_headers(client, username="resume-owner", password="secret", role="user")
    album = create_album(client, headers, name="Resume Album")

    list_response = client.get("/api/v1/albums", headers=headers)
    assert list_response.status_code == 200
    listed_album = next(item for item in list_response.json()["data"] if item["id"] == album["id"])
    assert listed_album["resume_step"] == "upload"
    assert listed_album["resume_route"] == f"/albums/{album['id']}/upload"

    upload_photo(client, headers, album["id"], "resume.jpg")
    detail_response = client.get(f"/api/v1/albums/{album['id']}", headers=headers)
    assert detail_response.status_code == 200
    detail_album = detail_response.json()["data"]
    assert detail_album["status"] == "uploaded"
    assert detail_album["resume_step"] == "cleaning"
    assert detail_album["resume_route"] == f"/albums/{album['id']}/cleaning"


def test_user_can_delete_own_project_and_related_album_files(client):
    settings = get_settings()
    headers = create_auth_headers(client, username="project-delete-owner", password="secret", role="user")

    project_response = client.get("/api/v1/users/me/projects", headers=headers)
    assert project_response.status_code == 200
    project = project_response.json()["data"][0]

    album = create_album(client, headers, name="Delete Album")
    photo = upload_photo(client, headers, album["id"], "delete-me.jpg")

    export_dir = Path(settings.uploads_dir) / f"albums/{album['id']}/exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / "mock-export.html"
    export_path.write_text("<html>export</html>", encoding="utf-8")

    create_export = client.post(
        f"/api/v1/albums/{album['id']}/export",
        headers=headers,
    )
    assert create_export.status_code == 400

    # Create a mock export row through successful HTML export pipeline prerequisites.
    chapter_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "删除章节", "description": "desc", "photo_ids": [photo["id"]]},
        headers=headers,
    )
    assert chapter_response.status_code == 200
    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 200
    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 200
    export_response = client.post(f"/api/v1/albums/{album['id']}/export", headers=headers)
    assert export_response.status_code == 200
    export_record = export_response.json()["data"]

    uploads_root = Path(settings.uploads_dir)
    photo_path = uploads_root / photo["storage_key"]
    export_storage_path = uploads_root / export_record["file_path"]
    assert photo_path.exists()
    assert export_storage_path.exists()

    delete_response = client.delete(f"/api/v1/users/me/projects/{project['id']}", headers=headers)
    assert delete_response.status_code == 200
    payload = delete_response.json()["data"]
    assert payload["project_id"] == project["id"]
    assert payload["deleted_album_count"] >= 1

    projects_response = client.get("/api/v1/users/me/projects", headers=headers)
    assert projects_response.status_code == 200
    project_ids = [item["id"] for item in projects_response.json()["data"]]
    assert project["id"] not in project_ids

    album_response = client.get(f"/api/v1/albums/{album['id']}", headers=headers)
    assert album_response.status_code == 404
    assert not photo_path.exists()
    assert not export_storage_path.exists()


def test_user_cannot_delete_other_users_project(client):
    owner_headers = create_auth_headers(client, username="project-owner-a", password="secret", role="user")
    other_headers = create_auth_headers(client, username="project-owner-b", password="secret", role="user")

    projects_response = client.get("/api/v1/users/me/projects", headers=owner_headers)
    assert projects_response.status_code == 200
    project_id = projects_response.json()["data"][0]["id"]

    delete_response = client.delete(f"/api/v1/users/me/projects/{project_id}", headers=other_headers)
    assert delete_response.status_code == 403
    assert delete_response.json()["detail"] == "Forbidden"


def test_delete_project_rejects_when_active_tasks_exist(client):
    headers = create_auth_headers(client, username="active-task-owner", password="secret", role="user")
    project_response = client.get("/api/v1/users/me/projects", headers=headers)
    assert project_response.status_code == 200
    project_id = project_response.json()["data"][0]["id"]

    album = create_album(client, headers, name="Task Locked Album")

    async def seed_running_task() -> None:
        async with db_session.AsyncSessionFactory() as session:
            session.add(
                Task(
                    album_id=album["id"],
                    task_type="export_pdf",
                    task_status=TaskStatus.RUNNING,
                )
            )
            await session.commit()

    asyncio.run(seed_running_task())

    delete_response = client.delete(f"/api/v1/users/me/projects/{project_id}", headers=headers)
    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == "project has running tasks"
