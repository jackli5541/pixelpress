from fastapi.testclient import TestClient

from pixelpress_backend.main import app
from pixelpress_backend.repositories.memory import store


client = TestClient(app)


def setup_function():
    store.albums.clear()
    store.tasks.clear()
    store.layouts.clear()
    store.operations.clear()
    store.idempotency_map.clear()


def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_layout_success():
    payload = {
        "album_id": "album-001",
        "idempotency_key": "idem-001",
        "scene_mode": "annual",
        "photo_ids": ["p1", "p2", "p3"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    response = client.post("/api/v1/layouts/generate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["task_status"] == "completed"
    assert body["album_status"] == "reviewable"
    assert body["book_layout_version"] == 1


def test_generate_layout_version_conflict():
    first_payload = {
        "album_id": "album-002",
        "idempotency_key": "idem-002",
        "scene_mode": "annual",
        "photo_ids": ["p1"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    first_response = client.post("/api/v1/layouts/generate", json=first_payload)
    assert first_response.status_code == 200

    second_payload = {
        "album_id": "album-002",
        "idempotency_key": "idem-003",
        "scene_mode": "annual",
        "photo_ids": ["p1"],
        "base_version": 999,
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    second_response = client.post("/api/v1/layouts/generate", json=second_payload)
    assert second_response.status_code == 409


def test_submit_operation_creates_partial_task():
    generate_payload = {
        "album_id": "album-003",
        "idempotency_key": "idem-004",
        "scene_mode": "annual",
        "photo_ids": ["p1"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    generate_response = client.post("/api/v1/layouts/generate", json=generate_payload)
    assert generate_response.status_code == 200

    operation_payload = {
        "operation_id": "op-001",
        "album_id": "album-003",
        "base_version": 1,
        "op": "replace_photo",
        "payload": {"page_id": "page-001", "photo_id": "p2"},
        "actor": {"type": "user", "id": "user-001"},
    }
    operation_response = client.post("/api/v1/operations", json=operation_payload)
    assert operation_response.status_code == 200
    body = operation_response.json()
    assert body["accepted"] is True
    assert body["next_task_id"] is not None
