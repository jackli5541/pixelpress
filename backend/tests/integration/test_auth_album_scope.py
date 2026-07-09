from __future__ import annotations


def test_users_me_requires_authentication(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_register_and_login_flow(client):
    register_response = client.post("/api/v1/auth/register", json={"username": "alice", "password": "secret"})
    assert register_response.status_code == 200
    assert register_response.json()["data"]["username"] == "alice"
    assert register_response.json()["data"]["role"] == "user"

    login_response = client.post("/api/v1/auth/login", json={"username": "alice", "password": "secret"})
    assert login_response.status_code == 200
    payload = login_response.json()["data"]
    assert payload["token_type"] == "bearer"
    assert isinstance(payload["access_token"], str)


def test_album_detail_404_for_missing_album(client):
    register = client.post("/api/v1/auth/register", json={"username": "reader", "password": "secret"})
    assert register.status_code == 200
    login = client.post("/api/v1/auth/login", json={"username": "reader", "password": "secret"})
    token = login.json()["data"]["access_token"]
    response = client.get(
        "/api/v1/albums/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "album not found"


def test_preview_requires_existing_rendered_album(client):
    register = client.post("/api/v1/auth/register", json={"username": "previewer", "password": "secret"})
    assert register.status_code == 200
    login = client.post("/api/v1/auth/login", json={"username": "previewer", "password": "secret"})
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/api/v1/albums",
        json={"name": "测试相册", "album_type": "yearbook", "book_size": "square_10inch", "theme_style": "minimal"},
        headers=headers,
    )
    album_id = create_response.json()["data"]["id"]

    preview_response = client.get(
        f"/api/v1/albums/{album_id}/preview",
        headers=headers,
    )
    assert preview_response.status_code == 400
    assert "not rendered yet" in preview_response.json()["detail"]
