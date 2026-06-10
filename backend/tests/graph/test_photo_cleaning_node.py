from __future__ import annotations

import pytest

from pixelpress_backend.graph.photo_cleaning_node import photo_cleaning_node
from pixelpress_backend.models.domain import (
    AlbumState,
    BookLayout,
    FeatureStatus,
    GenerateConstraints,
    GenerateLayoutRequest,
    PhotoAsset,
    PhotoExif,
    SceneMode,
    TaskState,
    TaskStatus,
    TaskType,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def test_photo_cleaning_node_with_empty_input():
    state = LayoutWorkflowState(
        request=GenerateLayoutRequest(
            album_id="album_001",
            idempotency_key="test_key_001",
            scene_mode=SceneMode.EVENT,
            book_size="A4_square",
            binding="hardcover",
            style="minimal",
            photo_ids=["photo_001"],
            photo_assets=[],
            photo_order="upload_order",
            force_mode="normal",
            constraints=GenerateConstraints(),
            base_version=None,
        ),
        album=AlbumState(album_id="album_001"),
        task=TaskState(
            task_id="task_001",
            album_id="album_001",
            task_type=TaskType.LAYOUT_GENERATE,
            status=TaskStatus.RUNNING,
            idempotency_key="test_key_001",
        ),
    )

    result = photo_cleaning_node(state)

    assert result.cleaned_photo_set is not None
    assert result.cleaned_photo_set.album_id == "album_001"
    assert len(result.cleaned_photo_set.valid_photos) == 1
    assert len(result.cleaned_photo_set.dropped_photos) == 0
    assert result.cleaned_photo_set.cleaning_summary.input_count == 1
    assert result.cleaned_photo_set.cleaning_summary.valid_count == 1


def test_photo_cleaning_node_with_assets():
    state = LayoutWorkflowState(
        request=GenerateLayoutRequest(
            album_id="album_002",
            idempotency_key="test_key_002",
            scene_mode=SceneMode.EVENT,
            book_size="A4_square",
            binding="hardcover",
            style="minimal",
            photo_ids=["photo_001", "photo_002"],
            photo_assets=[
                PhotoAsset(
                    photo_id="photo_001",
                    image_url=None,
                    width=1920,
                    height=1080,
                    orientation="landscape",
                    exif=PhotoExif(),
                ),
                PhotoAsset(
                    photo_id="photo_002",
                    image_url=None,
                    width=1080,
                    height=1920,
                    orientation="portrait",
                    exif=PhotoExif(),
                ),
            ],
            photo_order="upload_order",
            force_mode="normal",
            constraints=GenerateConstraints(),
            base_version=None,
        ),
        album=AlbumState(album_id="album_002"),
        task=TaskState(
            task_id="task_002",
            album_id="album_002",
            task_type=TaskType.LAYOUT_GENERATE,
            status=TaskStatus.RUNNING,
            idempotency_key="test_key_002",
        ),
    )

    result = photo_cleaning_node(state)

    assert result.cleaned_photo_set is not None
    assert len(result.cleaned_photo_set.valid_photos) == 2
    for photo in result.cleaned_photo_set.valid_photos:
        assert photo.photo_id in ["photo_001", "photo_002"]


def test_photo_cleaning_node_decision_values():
    state = LayoutWorkflowState(
        request=GenerateLayoutRequest(
            album_id="album_003",
            idempotency_key="test_key_003",
            scene_mode=SceneMode.EVENT,
            book_size="A4_square",
            binding="hardcover",
            style="minimal",
            photo_ids=["photo_001"],
            photo_assets=[],
            photo_order="upload_order",
            force_mode="normal",
            constraints=GenerateConstraints(),
            base_version=None,
        ),
        album=AlbumState(album_id="album_003"),
        task=TaskState(
            task_id="task_003",
            album_id="album_003",
            task_type=TaskType.LAYOUT_GENERATE,
            status=TaskStatus.RUNNING,
            idempotency_key="test_key_003",
        ),
    )

    result = photo_cleaning_node(state)

    for photo in result.cleaned_photo_set.valid_photos:
        assert photo.decision in ["keep", "deprioritize", "drop"]
        assert 0 <= photo.rank_weight <= 1.0