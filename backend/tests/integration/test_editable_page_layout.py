from __future__ import annotations

from .helpers import create_album, create_auth_headers, upload_photo


def test_page_layout_v3_round_trip_and_validation(client):
    headers = create_auth_headers(client, username="layout-editor", password="secret")
    album = create_album(client, headers, name="Editable Layout")
    first = upload_photo(client, headers, album["id"], "first.jpg")
    second = upload_photo(client, headers, album["id"], "second.jpg")
    created = client.post(
        f"/api/v1/albums/{album['id']}/pages",
        json={"template": "two_column", "photo_ids": [first["id"], second["id"]]},
        headers=headers,
    )
    assert created.status_code == 200
    page_id = created.json()["data"]["id"]

    listed = client.get(f"/api/v1/albums/{album['id']}/pages", headers=headers)
    assert listed.status_code == 200
    page = listed.json()["data"][0]
    assert page["meta"]["layout_version"] == 3
    assert page["meta"]["description"]["height"] >= 0.06
    assert {item["photo_id"] for item in page["meta"]["elements"]} == {first["id"], second["id"]}

    page["meta"]["description"]["text"] = "只在页描述框中显示"
    page["meta"]["description"]["height"] = 0.063
    saved = client.patch(
        f"/api/v1/albums/{album['id']}/pages/{page_id}",
        json={"meta": page["meta"]},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["meta"]["description"]["text"] == "只在页描述框中显示"
    assert saved.json()["data"]["status"] == "draft"

    invalid = page["meta"]
    invalid["elements"][1]["x"] = invalid["elements"][0]["x"]
    invalid["elements"][1]["y"] = invalid["elements"][0]["y"]
    rejected = client.patch(
        f"/api/v1/albums/{album['id']}/pages/{page_id}",
        json={"meta": invalid},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert "overlap" in rejected.text

    too_short = saved.json()["data"]["meta"]
    too_short["description"]["height"] = 0.01
    rejected = client.patch(
        f"/api/v1/albums/{album['id']}/pages/{page_id}",
        json={"meta": too_short},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert "too small" in rejected.text
