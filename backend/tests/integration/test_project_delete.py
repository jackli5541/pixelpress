from __future__ import annotations

import asyncio

from app.common.enums import TaskStatus
from app.db import session as db_session
from app.models.task import Task
from .helpers import create_album, create_auth_headers


def test_user_cannot_delete_their_only_project(client):
    headers = create_auth_headers(client, username="project-delete-owner", password="secret", role="user")
    project = client.get("/api/v1/users/me/projects", headers=headers).json()["data"][0]
    response = client.delete(f"/api/v1/users/me/projects/{project['id']}", headers=headers)
    assert response.status_code == 409
    assert response.json()["message"] == "projects are managed by administrators"


def test_admin_can_delete_empty_project_but_not_project_with_albums(client):
    admin_headers = create_auth_headers(client, username="project-delete-admin", password="secret", role="admin")
    owner_headers = create_auth_headers(client, username="project-delete-owner-2", password="secret", role="user")
    project = client.get("/api/v1/users/me/projects", headers=owner_headers).json()["data"][0]
    create_album(client, owner_headers, name="Protected Album")
    blocked = client.delete(f"/api/v1/admin/projects/{project['id']}", headers=admin_headers)
    assert blocked.status_code == 409
    assert blocked.json()["message"] == "project still contains albums; move or delete those albums first"


def test_admin_delete_rejects_running_tasks(client):
    admin_headers = create_auth_headers(client, username="project-delete-admin-2", password="secret", role="admin")
    owner_headers = create_auth_headers(client, username="project-delete-owner-3", password="secret", role="user")
    project = client.get("/api/v1/users/me/projects", headers=owner_headers).json()["data"][0]
    album = create_album(client, owner_headers, name="Task Locked Album")

    async def seed_running_task() -> None:
        async with db_session.AsyncSessionFactory() as session:
            session.add(Task(album_id=album["id"], task_type="export_pdf", task_status=TaskStatus.RUNNING))
            await session.commit()

    asyncio.run(seed_running_task())
    response = client.delete(f"/api/v1/admin/projects/{project['id']}", headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["message"] == "project has running tasks"


def test_admin_force_delete_removes_project_and_its_albums(client):
    admin_headers = create_auth_headers(client, username="project-force-admin", password="secret", role="admin")
    owner_headers = create_auth_headers(client, username="project-force-owner", password="secret", role="user")
    project = client.get("/api/v1/users/me/projects", headers=owner_headers).json()["data"][0]
    album = create_album(client, owner_headers, name="Force Delete Album")

    response = client.delete(f"/api/v1/admin/projects/{project['id']}?force=true", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"]["deleted_album_count"] == 1
    missing_album = client.get(f"/api/v1/albums/{album['id']}", headers=owner_headers)
    assert missing_album.status_code == 404
