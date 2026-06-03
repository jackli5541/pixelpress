from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from pixelpress_backend.core.enums import (
    AlbumStatus,
    BookLayoutStatus,
    FeatureStatus,
    OperationType,
    SceneMode,
    TaskStatus,
    TaskType,
)
from pixelpress_backend.models.common import Actor, BaseSchema, JSONDict, utc_now


class GenerateConstraints(BaseSchema):
    must_include: list[str] = Field(default_factory=list)
    must_exclude: list[str] = Field(default_factory=list)
    hero_person_id: str | None = None
    min_pages: int = 20
    max_pages: int = 60
    avoid_spread: bool = False


class GenerateLayoutRequest(BaseSchema):
    album_id: str
    idempotency_key: str
    scene_mode: SceneMode
    book_size: str = "A4_square"
    binding: str = "hardcover"
    style: str = "minimal"
    photo_ids: list[str]
    photo_order: str = "upload_order"
    force_mode: str = "normal"
    constraints: GenerateConstraints = Field(default_factory=GenerateConstraints)
    base_version: int | None = None


class LayoutGenerateResponse(BaseSchema):
    task_id: str
    task_status: TaskStatus
    album_status: AlbumStatus
    book_layout_version: int | None = None
    estimated_seconds: int = 20


class BookLayout(BaseSchema):
    album_id: str
    version: int
    status: BookLayoutStatus = BookLayoutStatus.DRAFT
    base_version: int | None = None
    is_partial: bool = False
    pages: list[JSONDict] = Field(default_factory=list)
    chapters: list[JSONDict] = Field(default_factory=list)
    score_snapshot: JSONDict = Field(default_factory=dict)
    generation_meta: JSONDict = Field(default_factory=dict)
    render_snapshot: JSONDict = Field(default_factory=dict)
    export_snapshot: JSONDict = Field(default_factory=dict)


class AlbumState(BaseSchema):
    album_id: str
    status: AlbumStatus = AlbumStatus.DRAFT
    current_layout_version: int | None = None
    latest_completed_task_id: str | None = None
    allow_preview: bool = False
    allow_export: bool = False
    allow_order: bool = False
    feature_status: FeatureStatus = FeatureStatus.PENDING


class TaskState(BaseSchema):
    task_id: str
    album_id: str
    task_type: TaskType
    status: TaskStatus
    idempotency_key: str
    base_version: int | None = None
    result_version: int | None = None
    error_code: str | None = None
    degrade_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UserOperation(BaseSchema):
    operation_id: str
    album_id: str
    base_version: int
    op_type: OperationType
    payload: JSONDict = Field(default_factory=dict)
    actor: Actor
    created_at: datetime = Field(default_factory=utc_now)


class RepairHint(BaseSchema):
    target: str
    action: str


class LayoutWorkflowState(BaseSchema):
    request: GenerateLayoutRequest
    album: AlbumState
    task: TaskState
    cleaned_photo_set: JSONDict = Field(default_factory=dict)
    chapter_plan: JSONDict = Field(default_factory=dict)
    page_plan: JSONDict = Field(default_factory=dict)
    page_layouts: JSONDict = Field(default_factory=dict)
    score_snapshot: JSONDict = Field(default_factory=dict)
    repair_hints: list[RepairHint] = Field(default_factory=list)
    decision: str | None = None
    final_layout: BookLayout | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskStatusResponse(BaseSchema):
    task_id: str
    task_status: TaskStatus
    album_status: AlbumStatus
    result: JSONDict | None = None
    error: JSONDict | None = None
