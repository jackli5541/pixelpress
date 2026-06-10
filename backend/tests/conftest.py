from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path

import pytest

from pixelpress_backend.core.enums import FeatureStatus, SceneMode, TaskStatus, TaskType
from pixelpress_backend.models.domain import (
    AlbumState,
    GenerateConstraints,
    GenerateLayoutRequest,
    TaskState,
)
from pixelpress_backend.models.workflow_contracts import (
    ChapterPlan,
    CleanedPhotoSet,
    GeneratedPageLayout,
    PagePlan,
    ScoreSnapshot,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState
from pixelpress_backend.repositories.memory import store


def _default_request() -> GenerateLayoutRequest:
    return GenerateLayoutRequest(
        album_id="album-test",
        idempotency_key="idem-test",
        scene_mode=SceneMode.ANNUAL,
        photo_ids=["p1", "p2", "p3"],
        constraints=GenerateConstraints(min_pages=1, max_pages=10),
    )


def _default_album_state() -> AlbumState:
    return AlbumState(
        album_id="album-test",
        feature_status=FeatureStatus.READY,
    )


def _default_task_state() -> TaskState:
    return TaskState(
        task_id="task-test",
        album_id="album-test",
        task_type=TaskType.LAYOUT_GENERATE,
        status=TaskStatus.RUNNING,
        idempotency_key="idem-test",
    )


@pytest.fixture(autouse=True)
def reset_memory_store():
    store.albums.clear()
    store.tasks.clear()
    store.layouts.clear()
    store.operations.clear()
    store.operation_receipts.clear()
    store.idempotency_map.clear()


@pytest.fixture
def workflow_state_factory() -> Callable[..., LayoutWorkflowState]:
    def _factory(
        *,
        cleaned_photo_set: dict | CleanedPhotoSet | None = None,
        chapter_plan: dict | ChapterPlan | None = None,
        page_plan: dict | PagePlan | None = None,
        page_layouts: list[dict] | list[GeneratedPageLayout] | None = None,
        score_snapshot: dict | ScoreSnapshot | None = None,
    ) -> LayoutWorkflowState:
        state_data = {
            "request": _default_request(),
            "album": _default_album_state(),
            "task": _default_task_state(),
        }
        if cleaned_photo_set is not None:
            state_data["cleaned_photo_set"] = cleaned_photo_set
        if chapter_plan is not None:
            state_data["chapter_plan"] = chapter_plan
        if page_plan is not None:
            state_data["page_plan"] = page_plan
        if page_layouts is not None:
            state_data["page_layouts"] = page_layouts
        if score_snapshot is not None:
            state_data["score_snapshot"] = score_snapshot
        return LayoutWorkflowState(
            **state_data,
        )

    return _factory


@pytest.fixture
def cleaned_photo_set_fixture() -> dict:
    return {
        "album_id": "album-test",
        "valid_photos": [
            {"photo_id": "p1", "decision": "keep", "rank_weight": 1.0},
            {"photo_id": "p2", "decision": "keep", "rank_weight": 0.9},
            {"photo_id": "p3", "decision": "deprioritize", "rank_weight": 0.5},
        ],
        "dropped_photos": [],
    }


@pytest.fixture
def chapter_plan_fixture() -> dict:
    return {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "测试章节",
                "photo_ids": ["p1", "p2", "p3"],
            }
        ],
    }


@pytest.fixture
def page_plan_fixture() -> dict:
    return {
        "total_pages": 1,
        "planned_pages": [
            {
                "page_id": "page-001",
                "chapter_id": "chapter-001",
                "page_role": "chapter_opening",
                "candidate_photo_ids": ["p1"],
                "layout_family": "single_full_bleed",
                "text_need": "chapter_title",
            }
        ],
    }


@pytest.fixture
def page_layouts_fixture() -> list[dict]:
    return [
        {
            "page_id": "page-001",
            "template_id": "tpl_single_full_bleed",
            "layout_score": 0.8,
            "slots": [],
            "text_blocks": [],
        }
    ]


@pytest.fixture
def json_artifact_writer() -> Callable[[str, object], Path]:
    artifact_root = Path(__file__).resolve().parent / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    def _write(relative_path: str, payload: object) -> Path:
        output_path = artifact_root / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    return _write
