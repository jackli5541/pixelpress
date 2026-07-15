from __future__ import annotations

from .helpers import create_auth_headers


def test_user_can_list_own_projects_and_create_album_with_selected_project(client):
    headers = create_auth_headers(client, username="project-owner", password="secret", role="user")

    projects_response = client.get("/api/v1/users/me/projects", headers=headers)
    assert projects_response.status_code == 200
    projects = projects_response.json()["data"]
    assert len(projects) == 1

    project_id = projects[0]["id"]
    create_album = client.post(
        "/api/v1/albums",
        json={
            "name": "Owner Album",
            "project_id": project_id,
            "album_type": "yearbook",
            "book_size": "square_10inch",
            "theme_style": "minimal",
        },
        headers=headers,
    )
    assert create_album.status_code == 200
    assert create_album.json()["data"]["project_id"] == project_id


def test_user_cannot_create_album_under_another_users_project(client):
    owner_headers = create_auth_headers(client, username="owner-a", password="secret", role="user")
    other_headers = create_auth_headers(client, username="owner-b", password="secret", role="user")

    owner_projects = client.get("/api/v1/users/me/projects", headers=owner_headers)
    assert owner_projects.status_code == 200
    owner_project_id = owner_projects.json()["data"][0]["id"]

    response = client.post(
        "/api/v1/albums",
        json={
            "name": "Cross Project Album",
            "project_id": owner_project_id,
            "album_type": "yearbook",
            "book_size": "square_10inch",
            "theme_style": "minimal",
        },
        headers=other_headers,
    )
    assert response.status_code == 403
    assert response.json()["message"] == "project not found or inaccessible"
