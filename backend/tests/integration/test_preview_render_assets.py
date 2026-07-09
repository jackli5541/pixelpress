from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


def test_preview_html_uses_signed_render_asset_urls(client):
    headers = create_auth_headers(client, username="preview-assets-admin", password="secret", role="admin")
    album = create_album(client, headers, name="Preview Assets")
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

    preview_response = client.get(f"/api/v1/albums/{album['id']}/preview", headers=headers)
    assert preview_response.status_code == 200
    html = preview_response.json()["data"]["html"]
    assert "data:image/jpeg;base64," not in html

    marker = f'/api/v1/render-assets/albums/{album["id"]}/photos/'
    start = html.index(marker)
    end = html.index('"', start)
    signed_url = html[start:end]
    parsed = urlparse(signed_url)
    params = parse_qs(parsed.query)
    assert params["token"][0]
    assert params["exp"][0]
    assert params["rev"][0] == "1"

    asset_response = client.get(signed_url)
    assert asset_response.status_code == 200
    assert asset_response.headers["content-type"].startswith("image/")
    assert asset_response.content
