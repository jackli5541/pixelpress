from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import get_settings
from sqlalchemy import select

from app.db import session as db_session
from app.models.album import Album
from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


async def _get_album(album_id: str) -> Album:
    async with db_session.AsyncSessionFactory() as session:
        result = await session.execute(select(Album).where(Album.id == album_id))
        return result.scalar_one()


def test_rerender_prunes_previous_render_artifacts(client):
    headers = create_auth_headers(client, username="cleanup-admin", password="secret", role="admin")
    album = create_album(client, headers, name="Cleanup Album")
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

    settings = get_settings()
    album_model = asyncio.run(_get_album(album["id"]))
    first_preview = Path(settings.uploads_dir) / album_model.preview_html_path
    first_print = Path(settings.uploads_dir) / album_model.print_html_path
    first_manifest = Path(settings.uploads_dir) / album_model.render_manifest_path
    assert first_preview.exists()
    assert first_print.exists()
    assert first_manifest.exists()

    patch_response = client.patch(
        f"/api/v1/albums/{album['id']}",
        json={"cover_title": "Rerender Me"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert not first_preview.exists()
    assert not first_print.exists()
    assert not first_manifest.exists()

    rerender_plan = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert rerender_plan.status_code == 202
    run_task_worker(rerender_plan.json()["data"]["task"])

    rerender_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert rerender_response.status_code == 202
    run_task_worker(rerender_response.json()["data"]["task"])

    updated = asyncio.run(_get_album(album["id"]))
    second_preview = Path(settings.uploads_dir) / updated.preview_html_path
    second_print = Path(settings.uploads_dir) / updated.print_html_path
    second_manifest = Path(settings.uploads_dir) / updated.render_manifest_path
    assert second_preview.exists()
    assert second_print.exists()
    assert second_manifest.exists()
