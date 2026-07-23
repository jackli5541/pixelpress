from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings

from .helpers import create_auth_headers, run_task_worker, upload_photo


def test_spread_v2_plan_style_preview_render_and_export_cache(client) -> None:
    headers = create_auth_headers(client, username="spread-v2-owner", password="secret")
    created = client.post(
        "/api/v1/albums",
        json={
            "name": "Spread V2 Album",
            "album_type": "yearbook",
            "book_size": "square_10inch",
            "theme_style": "minimal_white",
            "layout_version": "spread_v2",
        },
        headers=headers,
    )
    assert created.status_code == 200
    album = created.json()["data"]
    photos = [upload_photo(client, headers, album["id"], f"{index}.jpg") for index in range(7)]
    chapter = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={
            "name": "First chapter",
            "description": "A short chapter description.",
            "photo_ids": [photo["id"] for photo in photos],
        },
        headers=headers,
    )
    assert chapter.status_code == 200

    plan = client.post(f"/api/v1/albums/{album['id']}/plan?layout_version=spread_v2", headers=headers)
    assert plan.status_code == 202
    run_task_worker(plan.json()["data"]["task"])

    spreads_response = client.get(f"/api/v1/albums/{album['id']}/spreads", headers=headers)
    assert spreads_response.status_code == 200
    spreads = spreads_response.json()["data"]
    assigned = [photo_id for spread in spreads for page in spread["pages"] for photo_id in page["photo_ids"]]
    assert len(assigned) == 7
    assert len(set(assigned)) == 7
    assert all(spread["needs_review"] for spread in spreads)
    selectable = next(spread for spread in spreads if len(spread["meta"]["candidate_recipe_keys"]) > 1)
    candidate_key = next(key for key in selectable["meta"]["candidate_recipe_keys"] if key != selectable["recipe_key"])
    sample = client.get(
        f"/api/v1/albums/{album['id']}/preview?sample=true&style_key=minimal_white&spread_id={selectable['id']}&recipe_key={candidate_key}",
        headers=headers,
    )
    assert sample.status_code == 200
    switched = client.patch(
        f"/api/v1/albums/{album['id']}/spreads/{selectable['id']}",
        json={"recipe_key": candidate_key},
        headers=headers,
    )
    assert switched.status_code == 200
    assert switched.json()["data"]["recipe_key"] == candidate_key
    assert {photo_id for page in switched.json()["data"]["pages"] for photo_id in page["photo_ids"]} == {
        photo_id for page in selectable["pages"] for photo_id in page["photo_ids"]
    }

    for style_key in ("minimal_white", "editorial_journal", "warm_memory"):
        sample = client.get(
            f"/api/v1/albums/{album['id']}/preview?sample=true&style_key={style_key}",
            headers=headers,
        )
        assert sample.status_code == 200
        assert "spread-v2" in sample.json()["data"]["html"]

    render = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render.status_code == 202
    run_task_worker(render.json()["data"]["task"])

    settings = get_settings()
    detail = client.get(f"/api/v1/albums/{album['id']}", headers=headers).json()["data"]
    print_html = (Path(settings.uploads_dir) / detail["print_html_path"]).read_text(encoding="utf-8")
    manifest = json.loads((Path(settings.uploads_dir) / detail["render_manifest_path"]).read_text(encoding="utf-8"))
    assert "base64," not in print_html
    assert len(print_html.encode("utf-8")) < 2 * 1024 * 1024
    assert manifest["pdf_page_count"] == manifest["page_count"]
    assert manifest["spread_count"] == len(spreads)
    assert manifest["blank_page_count"] >= 1
    assert manifest["print_assets"]

    first_export = client.post(f"/api/v1/albums/{album['id']}/export?format=html", headers=headers)
    assert first_export.status_code == 202
    run_task_worker(first_export.json()["data"]["task"])
    cached_export = client.post(f"/api/v1/albums/{album['id']}/export?format=html", headers=headers)
    assert cached_export.status_code == 202
    assert cached_export.json()["data"]["cache_hit"] is True
    assert cached_export.json()["data"]["export"]["render_revision"] == detail["render_revision"]
