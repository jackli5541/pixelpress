from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import session as db_session
from app.models.album import Album
from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


async def _get_album(album_id: str) -> Album:
    async with db_session.AsyncSessionFactory() as session:
        result = await session.execute(select(Album).where(Album.id == album_id))
        return result.scalar_one()


def test_album_patch_invalidation_clears_render_artifacts_and_bumps_content_revision(client):
    headers = create_auth_headers(client, username="invalidate-owner", password="secret", role="admin")
    album = create_album(client, headers, name="Invalidate Album")
    p1 = upload_photo(client, headers, album["id"], "a.jpg")
    p2 = upload_photo(client, headers, album["id"], "b.jpg")

    chapter_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "Chapter", "description": "desc", "photo_ids": [p1["id"], p2["id"]]},
        headers=headers,
    )
    assert chapter_response.status_code == 200

    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 202
    run_task_worker(plan_response.json()["data"]["task"])

    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 202
    run_task_worker(render_response.json()["data"]["task"])

    rendered = asyncio.run(_get_album(album["id"]))
    assert rendered.render_revision == 1
    assert rendered.preview_html_path == f"albums/{album['id']}/artifacts/r1/preview.html"
    previous_content_revision = rendered.content_revision

    patch_response = client.patch(
        f"/api/v1/albums/{album['id']}",
        json={"cover_title": "New Cover Title"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    payload = patch_response.json()["data"]
    assert payload["cover_title"] == "New Cover Title"
    assert payload["has_preview_artifact"] is False
    assert payload["has_print_artifact"] is False
    assert payload["has_render_manifest"] is False

    updated = asyncio.run(_get_album(album["id"]))
    assert updated.content_revision == previous_content_revision + 1
    assert updated.cover_title == "New Cover Title"
    assert updated.preview_html_path is None
    assert updated.print_html_path is None
    assert updated.render_manifest_path is None
    assert updated.full_html is None
    assert updated.status == "planned"
