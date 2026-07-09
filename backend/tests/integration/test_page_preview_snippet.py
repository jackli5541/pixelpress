from __future__ import annotations

from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


def test_page_listing_returns_preview_snippet_not_full_html_contract(client):
    headers = create_auth_headers(client, username="page-snippet-admin", password="secret", role="admin")
    album = create_album(client, headers, name="Page Snippet Album")
    p1 = upload_photo(client, headers, album["id"], "a.jpg")
    p2 = upload_photo(client, headers, album["id"], "b.jpg")

    chapter_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "章节A", "description": "desc", "photo_ids": [p1["id"], p2["id"]]},
        headers=headers,
    )
    assert chapter_response.status_code == 200

    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 202
    run_task_worker(plan_response.json()["data"]["task"])

    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 202
    run_task_worker(render_response.json()["data"]["task"])

    pages_response = client.get(f"/api/v1/albums/{album['id']}/pages", headers=headers)
    assert pages_response.status_code == 200
    pages = pages_response.json()["data"]
    assert pages
    first_page = pages[0]
    assert "html" not in first_page
    assert first_page["preview_available"] is True
    assert first_page["preview_snippet"]
    assert len(first_page["preview_snippet"]) <= 800
