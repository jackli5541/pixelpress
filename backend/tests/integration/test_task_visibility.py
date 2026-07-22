from __future__ import annotations

from .helpers import create_auth_headers, run_task_worker


def test_tasks_require_admin_authentication(client):
    response = client.get("/api/v1/tasks")
    assert response.status_code == 401
    assert response.json()["message"] == "Not authenticated"


def test_tasks_can_be_filtered_by_album_id(client):
    headers = create_auth_headers(client, username="admin2", password="secret", role="admin")

    album_1 = client.post(
        "/api/v1/albums",
        json={"name": "相册1", "album_type": "yearbook", "book_size": "square_10inch", "theme_style": "minimal"},
        headers=headers,
    ).json()["data"]
    album_2 = client.post(
        "/api/v1/albums",
        json={"name": "相册2", "album_type": "yearbook", "book_size": "square_10inch", "theme_style": "minimal"},
        headers=headers,
    ).json()["data"]

    cluster_1 = client.post(
        f"/api/v1/albums/{album_1['id']}/cluster",
        headers=headers,
    )
    assert cluster_1.status_code == 202
    run_task_worker(cluster_1.json()["data"]["task"])

    cluster_2 = client.post(
        f"/api/v1/albums/{album_2['id']}/cluster",
        headers=headers,
    )
    assert cluster_2.status_code == 202
    run_task_worker(cluster_2.json()["data"]["task"])

    filtered = client.get(f"/api/v1/tasks?album_id={album_1['id']}", headers=headers)
    assert filtered.status_code == 200
    tasks = filtered.json()["data"]
    assert tasks
    assert all(task["album_id"] == album_1["id"] for task in tasks)


def test_task_lookup_404_for_missing_task(client):
    headers = create_auth_headers(client, username="admin1", password="secret", role="admin")
    response = client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000001", headers=headers)
    assert response.status_code == 404
    assert response.json()["message"] == "task not found"
