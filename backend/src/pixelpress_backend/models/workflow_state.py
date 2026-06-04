from __future__ import annotations

from typing import Any

from pydantic import Field

from pixelpress_backend.core.enums import LayoutDecision
from pixelpress_backend.models.common import BaseSchema
from pixelpress_backend.models.domain import AlbumState, BookLayout, GenerateLayoutRequest, RepairHint, TaskState
from pixelpress_backend.models.workflow_contracts import (
    ChapterPlan,
    CleanedPhotoSet,
    GeneratedPageLayout,
    PagePlan,
    ScoreSnapshot,
)


class LayoutWorkflowState(BaseSchema):
    request: GenerateLayoutRequest
    album: AlbumState
    task: TaskState
    cleaned_photo_set: CleanedPhotoSet | None = None
    chapter_plan: ChapterPlan | None = None
    page_plan: PagePlan | None = None
    page_layouts: list[GeneratedPageLayout] | None = None
    score_snapshot: ScoreSnapshot = Field(default_factory=ScoreSnapshot)
    repair_hints: list[RepairHint] = Field(default_factory=list)
    decision: LayoutDecision | None = None
    final_layout: BookLayout | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
