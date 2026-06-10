from unittest.mock import patch

from fastapi.testclient import TestClient

from pixelpress_backend.main import app
from pixelpress_backend.repositories.memory import store


client = TestClient(app)


def setup_function():
    store.albums.clear()
    store.tasks.clear()
    store.layouts.clear()
    store.operations.clear()
    store.operation_receipts.clear()
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


def test_submit_operation_rejects_stale_base_version():
    first_generate_payload = {
        "album_id": "album-004",
        "idempotency_key": "idem-005",
        "scene_mode": "annual",
        "photo_ids": ["p1"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    assert client.post("/api/v1/layouts/generate", json=first_generate_payload).status_code == 200

    second_generate_payload = {
        "album_id": "album-004",
        "idempotency_key": "idem-006",
        "scene_mode": "annual",
        "photo_ids": ["p1", "p2"],
        "base_version": 1,
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    assert client.post("/api/v1/layouts/generate", json=second_generate_payload).status_code == 200

    stale_operation_payload = {
        "operation_id": "op-stale",
        "album_id": "album-004",
        "base_version": 1,
        "expected_status": "draft",
        "op": "replace_photo",
        "payload": {"page_id": "page-001", "photo_id": "p2"},
        "actor": {"type": "user", "id": "user-001"},
    }
    stale_response = client.post("/api/v1/operations", json=stale_operation_payload)
    assert stale_response.status_code == 409


def test_submit_operation_rejects_expected_status_mismatch():
    generate_payload = {
        "album_id": "album-005",
        "idempotency_key": "idem-007",
        "scene_mode": "annual",
        "photo_ids": ["p1"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    assert client.post("/api/v1/layouts/generate", json=generate_payload).status_code == 200

    operation_payload = {
        "operation_id": "op-status-mismatch",
        "album_id": "album-005",
        "base_version": 1,
        "expected_status": "locked",
        "op": "replace_photo",
        "payload": {"page_id": "page-001", "photo_id": "p2"},
        "actor": {"type": "user", "id": "user-001"},
    }
    response = client.post("/api/v1/operations", json=operation_payload)
    assert response.status_code == 400


def test_lock_partial_layout_is_rejected():
    generate_payload = {
        "album_id": "album-006",
        "idempotency_key": "idem-008",
        "scene_mode": "annual",
        "photo_ids": ["p1"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    assert client.post("/api/v1/layouts/generate", json=generate_payload).status_code == 200

    store.layouts["album-006"][1].is_partial = True
    operation_payload = {
        "operation_id": "op-lock-partial",
        "album_id": "album-006",
        "base_version": 1,
        "expected_status": "draft",
        "op": "lock_layout",
        "payload": {},
        "actor": {"type": "user", "id": "user-001"},
    }
    response = client.post("/api/v1/operations", json=operation_payload)
    assert response.status_code == 400


def test_submit_operation_is_idempotent():
    generate_payload = {
        "album_id": "album-007",
        "idempotency_key": "idem-009",
        "scene_mode": "annual",
        "photo_ids": ["p1"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    assert client.post("/api/v1/layouts/generate", json=generate_payload).status_code == 200

    operation_payload = {
        "operation_id": "op-idempotent",
        "album_id": "album-007",
        "base_version": 1,
        "expected_status": "draft",
        "op": "replace_photo",
        "payload": {"page_id": "page-001", "photo_id": "p2"},
        "actor": {"type": "user", "id": "user-001"},
    }
    first_response = client.post("/api/v1/operations", json=operation_payload)
    second_response = client.post("/api/v1/operations", json=operation_payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json() == second_response.json()
    assert len(store.operations) == 1
    assert len(store.tasks) == 2


def test_request_export_creates_export_task_for_locked_layout():
    generate_payload = {
        "album_id": "album-008",
        "idempotency_key": "idem-010",
        "scene_mode": "annual",
        "photo_ids": ["p1"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }
    assert client.post("/api/v1/layouts/generate", json=generate_payload).status_code == 200

    lock_payload = {
        "operation_id": "op-lock-exportable",
        "album_id": "album-008",
        "base_version": 1,
        "expected_status": "draft",
        "op": "lock_layout",
        "payload": {},
        "actor": {"type": "user", "id": "user-001"},
    }
    lock_response = client.post("/api/v1/operations", json=lock_payload)
    assert lock_response.status_code == 200

    export_payload = {
        "operation_id": "op-request-export",
        "album_id": "album-008",
        "base_version": 1,
        "expected_status": "locked",
        "op": "request_export",
        "payload": {},
        "actor": {"type": "user", "id": "user-001"},
    }
    export_response = client.post("/api/v1/operations", json=export_payload)
    assert export_response.status_code == 200
    assert export_response.json()["next_task_id"] is not None


def test_generate_layout_partial_result_marks_task_partial():
    generate_payload = {
        "album_id": "album-009",
        "idempotency_key": "idem-011",
        "scene_mode": "annual",
        "photo_ids": ["p1", "p2"],
        "constraints": {
            "min_pages": 1,
            "max_pages": 10,
        },
    }

    def _partial_invoke(state):
        state["final_layout"] = {
            "album_id": "album-009",
            "version": 1,
            "status": "draft",
            "base_version": None,
            "is_partial": True,
            "pages": [],
            "chapters": [],
            "score_snapshot": {},
            "generation_meta": {},
            "render_snapshot": {},
            "export_snapshot": {},
        }
        return state

    with patch("pixelpress_backend.services.layout_service.layout_workflow.invoke", side_effect=_partial_invoke):
        response = client.post("/api/v1/layouts/generate", json=generate_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["task_status"] == "partial"
    assert body["album_status"] == "reviewable"
    assert store.albums["album-009"].allow_export is False
    assert store.albums["album-009"].allow_order is False
