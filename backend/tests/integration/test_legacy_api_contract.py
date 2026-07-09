from __future__ import annotations

from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


def test_album_response_envelope_and_summary_counts(client):
    headers = create_auth_headers(client)
    album = create_album(client, headers)

    list_response = client.get("/api/v1/albums", headers=headers)
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["code"] == 0
    assert isinstance(list_payload["request_id"], str)
    assert list_payload["data"][0]["id"] == album["id"]

    summary_response = client.get(f"/api/v1/albums/{album['id']}/summary", headers=headers)
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()["data"]
    assert summary_payload["album"]["id"] == album["id"]
    assert summary_payload["photo_count"] == 0
    assert summary_payload["chapter_count"] == 0
    assert summary_payload["page_count"] == 0
    assert summary_payload["export_count"] == 0


def test_chapter_photo_ids_preserve_request_order_and_move_append_order(client):
    headers = create_auth_headers(client)
    album = create_album(client, headers)
    p1 = upload_photo(client, headers, album["id"], "a.jpg")
    p2 = upload_photo(client, headers, album["id"], "b.jpg")
    p3 = upload_photo(client, headers, album["id"], "c.jpg")

    chapter_1 = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={
            "name": "章节A",
            "description": "desc",
            "photo_ids": [p3["id"], p1["id"]],
        },
        headers=headers,
    )
    assert chapter_1.status_code == 200
    chapter_1_data = chapter_1.json()["data"]
    assert chapter_1_data["photo_ids"] == [p3["id"], p1["id"]]

    chapter_2 = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={
            "name": "章节B",
            "description": "desc",
            "photo_ids": [p2["id"]],
        },
        headers=headers,
    )
    assert chapter_2.status_code == 200
    chapter_2_data = chapter_2.json()["data"]

    move_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters/move-photos",
        json={
            "photo_ids": [p3["id"], p1["id"]],
            "target_chapter_id": chapter_2_data["id"],
        },
        headers=headers,
    )
    assert move_response.status_code == 200
    moved = move_response.json()["data"]["target_chapter"]
    assert moved["photo_ids"] == [p2["id"], p3["id"], p1["id"]]

    chapters_response = client.get(f"/api/v1/albums/{album['id']}/chapters", headers=headers)
    assert chapters_response.status_code == 200
    chapters = {item["id"]: item for item in chapters_response.json()["data"]}
    assert chapters[chapter_1_data["id"]]["photo_ids"] == []
    assert chapters[chapter_2_data["id"]]["photo_ids"] == [p2["id"], p3["id"], p1["id"]]


def test_page_photo_ids_preserve_request_order_and_move_append_order(client):
    headers = create_auth_headers(client)
    album = create_album(client, headers)
    p1 = upload_photo(client, headers, album["id"], "a.jpg")
    p2 = upload_photo(client, headers, album["id"], "b.jpg")
    p3 = upload_photo(client, headers, album["id"], "c.jpg")

    page_1 = client.post(
        f"/api/v1/albums/{album['id']}/pages",
        json={
            "chapter_id": None,
            "template": "grid_3",
            "photo_ids": [p3["id"], p1["id"]],
        },
        headers=headers,
    )
    assert page_1.status_code == 200
    page_1_data = page_1.json()["data"]
    assert page_1_data["photo_ids"] == [p3["id"], p1["id"]]

    page_2 = client.post(
        f"/api/v1/albums/{album['id']}/pages",
        json={
            "chapter_id": None,
            "template": "grid_3",
            "photo_ids": [p2["id"]],
        },
        headers=headers,
    )
    assert page_2.status_code == 200
    page_2_data = page_2.json()["data"]

    move_response = client.post(
        f"/api/v1/albums/{album['id']}/pages/move-photos",
        json={
            "photo_ids": [p3["id"], p1["id"]],
            "target_page_id": page_2_data["id"],
        },
        headers=headers,
    )
    assert move_response.status_code == 200
    moved = move_response.json()["data"]["target_page"]
    assert moved["photo_ids"] == [p2["id"], p3["id"], p1["id"]]

    pages_response = client.get(f"/api/v1/albums/{album['id']}/pages", headers=headers)
    assert pages_response.status_code == 200
    pages = {item["id"]: item for item in pages_response.json()["data"]}
    assert pages[page_1_data["id"]]["photo_ids"] == []
    assert pages[page_2_data["id"]]["photo_ids"] == [p2["id"], p3["id"], p1["id"]]


def test_preview_export_and_download_current_flow(client):
    headers = create_auth_headers(client, username="owner", password="secret", role="admin")
    album = create_album(client, headers)
    p1 = upload_photo(client, headers, album["id"], "a.jpg")
    p2 = upload_photo(client, headers, album["id"], "b.jpg")
    p3 = upload_photo(client, headers, album["id"], "c.jpg")

    chapter_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "章节A", "description": "desc", "photo_ids": [p1["id"], p2["id"], p3["id"]]},
        headers=headers,
    )
    assert chapter_response.status_code == 200

    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 202
    plan_task = plan_response.json()["data"]["task"]
    run_task_worker(plan_task)
    planned_pages_response = client.get(f"/api/v1/albums/{album['id']}/pages", headers=headers)
    assert planned_pages_response.status_code == 200
    planned_pages = planned_pages_response.json()["data"]
    assert planned_pages
    assert planned_pages[0]["photo_ids"] == [p1["id"], p2["id"], p3["id"]]

    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 202
    run_task_worker(render_response.json()["data"]["task"])

    preview_response = client.get(f"/api/v1/albums/{album['id']}/preview", headers=headers)
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]
    assert preview_payload["album_id"] == album["id"]
    assert "Print Album" in preview_payload["html"]
    assert "Chapter 01" in preview_payload["html"]
    assert "章节A" in preview_payload["html"]
    assert "/api/v1/render-assets/albums/" in preview_payload["html"]
    assert "data:image/jpeg;base64," not in preview_payload["html"]

    export_response = client.post(f"/api/v1/albums/{album['id']}/export", headers=headers)
    assert export_response.status_code == 202
    export_task = export_response.json()["data"]["task"]
    run_task_worker(export_task)

    exports_response = client.get(f"/api/v1/albums/{album['id']}/exports", headers=headers)
    assert exports_response.status_code == 200
    exports = exports_response.json()["data"]
    assert len(exports) == 1
    export_record = exports[0]
    assert export_record["album_id"] == album["id"]
    assert export_record["status"] == "completed"

    download_response = client.get(
        f"/api/v1/albums/{album['id']}/export/download/{export_record['id']}",
        headers=headers,
    )
    assert download_response.status_code == 200
    assert download_response.content
    assert b"data:image/jpeg;base64," in download_response.content

    assert exports[0]["id"] == export_record["id"]


def test_html_export_then_pdf_export_still_succeeds(client):
    headers = create_auth_headers(client, username="repeat-export-admin", password="secret", role="admin")
    album = create_album(client, headers)
    p1 = upload_photo(client, headers, album["id"], "a.jpg")
    p2 = upload_photo(client, headers, album["id"], "b.jpg")

    chapter_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "Repeat Export Chapter", "description": "desc", "photo_ids": [p1["id"], p2["id"]]},
        headers=headers,
    )
    assert chapter_response.status_code == 200

    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 202
    run_task_worker(plan_response.json()["data"]["task"])

    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 202
    run_task_worker(render_response.json()["data"]["task"])

    html_export_response = client.post(f"/api/v1/albums/{album['id']}/export?format=html", headers=headers)
    assert html_export_response.status_code == 202
    run_task_worker(html_export_response.json()["data"]["task"])

    album_after_html = client.get(f"/api/v1/albums/{album['id']}", headers=headers)
    assert album_after_html.status_code == 200
    assert album_after_html.json()["data"]["status"] == "exported"

    pdf_export_response = client.post(f"/api/v1/albums/{album['id']}/export?format=pdf", headers=headers)
    assert pdf_export_response.status_code == 202
    run_task_worker(pdf_export_response.json()["data"]["task"])

    exports_response = client.get(f"/api/v1/albums/{album['id']}/exports", headers=headers)
    assert exports_response.status_code == 200
    exports = exports_response.json()["data"]
    assert len(exports) == 2
    assert {item["format"] for item in exports} == {"html", "pdf"}

    pdf_export_record = next(item for item in exports if item["format"] == "pdf")
    download_response = client.get(
        f"/api/v1/albums/{album['id']}/export/download/{pdf_export_record['id']}",
        headers=headers,
    )
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith("application/pdf")
    assert download_response.content.startswith(b"%PDF")



def test_pdf_export_and_download_returns_real_pdf(client):
    headers = create_auth_headers(client, username="pdf-admin", password="secret", role="admin")
    album = create_album(client, headers)
    p1 = upload_photo(client, headers, album["id"], "a.jpg")
    p2 = upload_photo(client, headers, album["id"], "b.jpg")

    chapter_response = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "PDF Chapter", "description": "desc", "photo_ids": [p1["id"], p2["id"]]},
        headers=headers,
    )
    assert chapter_response.status_code == 200

    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 202
    run_task_worker(plan_response.json()["data"]["task"])

    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 202
    run_task_worker(render_response.json()["data"]["task"])

    export_response = client.post(f"/api/v1/albums/{album['id']}/export?format=pdf", headers=headers)
    assert export_response.status_code == 202
    export_task = export_response.json()["data"]["task"]
    run_task_worker(export_task)

    exports_response = client.get(f"/api/v1/albums/{album['id']}/exports", headers=headers)
    assert exports_response.status_code == 200
    export_record = exports_response.json()["data"][0]
    assert export_record["album_id"] == album["id"]
    assert export_record["format"] == "pdf"
    assert export_record["status"] == "completed"

    download_response = client.get(
        f"/api/v1/albums/{album['id']}/export/download/{export_record['id']}",
        headers=headers,
    )
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith("application/pdf")
    assert download_response.content.startswith(b"%PDF")


def test_tasks_endpoints_track_pipeline_status(client):
    headers = create_auth_headers(client, username="admin3", password="secret", role="admin")
    album = create_album(client, headers)
    upload_photo(client, headers, album["id"], "a.jpg")

    clean_response = client.post(f"/api/v1/albums/{album['id']}/clean", headers=headers)
    assert clean_response.status_code == 202
    clean_task = clean_response.json()["data"]["task"]
    run_task_worker(clean_task)

    tasks_response = client.get("/api/v1/tasks", headers=headers)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()["data"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == clean_task["id"]
    assert tasks[0]["task_status"] == "succeeded"

    get_task_response = client.get(f"/api/v1/tasks/{clean_task['id']}", headers=headers)
    assert get_task_response.status_code == 200
    assert get_task_response.json()["data"]["album_id"] == album["id"]


def test_album_task_endpoint_is_available_to_album_owner(client):
    headers = create_auth_headers(client)
    album = create_album(client, headers)
    upload_photo(client, headers, album["id"], "a.jpg")

    clean_response = client.post(f"/api/v1/albums/{album['id']}/clean", headers=headers)
    assert clean_response.status_code == 202
    clean_task = clean_response.json()["data"]["task"]
    run_task_worker(clean_task)

    tasks_response = client.get(f"/api/v1/albums/{album['id']}/tasks", headers=headers)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()["data"]
    assert tasks
    assert tasks[0]["id"] == clean_task["id"]

    filtered_response = client.get(f"/api/v1/albums/{album['id']}/tasks?task_type=clean_photos", headers=headers)
    assert filtered_response.status_code == 200
    filtered_tasks = filtered_response.json()["data"]
    assert len(filtered_tasks) == 1
    assert filtered_tasks[0]["task_type"] == "clean_photos"
