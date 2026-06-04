from __future__ import annotations

from typing import Literal

from pydantic import Field

from pixelpress_backend.core.enums import LayoutDecision, SceneMode
from pixelpress_backend.models.common import BaseSchema, JSONDict
from pixelpress_backend.models.domain import GenerateConstraints, GenerateLayoutRequest, RepairHint


class KeptPhoto(BaseSchema):
    photo_id: str
    decision: Literal["keep", "deprioritize"] = "keep"
    rank_weight: float = 1.0


class DroppedPhoto(BaseSchema):
    photo_id: str
    reason: str = "filtered"


class CleanedPhotoSet(BaseSchema):
    album_id: str
    valid_photos: list[KeptPhoto] = Field(default_factory=list)
    dropped_photos: list[DroppedPhoto] = Field(default_factory=list)


class PhotoCleaningInput(BaseSchema):
    request: GenerateLayoutRequest


class PhotoCleaningOutput(BaseSchema):
    cleaned_photo_set: CleanedPhotoSet


class ChapterPlanItem(BaseSchema):
    chapter_id: str
    order: int
    title_candidate: str
    photo_ids: list[str] = Field(default_factory=list)


class ChapterPlan(BaseSchema):
    album_id: str
    chapters: list[ChapterPlanItem] = Field(default_factory=list)


class ChapterClusteringInput(BaseSchema):
    album_id: str
    scene_mode: SceneMode
    cleaned_photo_set: CleanedPhotoSet


class ChapterClusteringOutput(BaseSchema):
    chapter_plan: ChapterPlan


class PlannedPage(BaseSchema):
    page_id: str
    chapter_id: str
    page_role: str
    candidate_photo_ids: list[str] = Field(default_factory=list)
    layout_family: str
    text_need: str


class PagePlan(BaseSchema):
    album_id: str
    total_pages: int
    planned_pages: list[PlannedPage] = Field(default_factory=list)


class PaginationPlanningInput(BaseSchema):
    album_id: str
    constraints: GenerateConstraints
    cleaned_photo_set: CleanedPhotoSet
    chapter_plan: ChapterPlan


class PaginationPlanningOutput(BaseSchema):
    page_plan: PagePlan


class GeneratedPageLayout(BaseSchema):
    page_id: str
    template_id: str
    layout_score: float = 0.0
    slots: list[JSONDict] = Field(default_factory=list)
    text_blocks: list[JSONDict] = Field(default_factory=list)
    placeholder: bool = True


class LayoutDraft(BaseSchema):
    album_id: str
    page_layouts: list[GeneratedPageLayout] = Field(default_factory=list)


class LayoutGenerationInput(BaseSchema):
    album_id: str
    page_plan: PagePlan


class LayoutGenerationOutput(BaseSchema):
    page_layouts: LayoutDraft


class SoftScoreSnapshot(BaseSchema):
    subject_salience: float = 0.0
    page_balance: float = 0.0
    story_coherence: float = 0.0
    layout_diversity: float = 0.0
    print_safety: float = 0.0


class GlobalScoreSnapshot(BaseSchema):
    overall: float = 0.0


class ScoreSnapshot(BaseSchema):
    hard_violations: list[str] = Field(default_factory=list)
    soft_scores: SoftScoreSnapshot = Field(default_factory=SoftScoreSnapshot)
    global_scores: GlobalScoreSnapshot = Field(default_factory=GlobalScoreSnapshot)


class BookScoringInput(BaseSchema):
    album_id: str
    chapter_plan: ChapterPlan
    page_plan: PagePlan
    page_layouts: LayoutDraft


class BookScoringOutput(BaseSchema):
    score_snapshot: ScoreSnapshot
    repair_hints: list[RepairHint] = Field(default_factory=list)
    decision: LayoutDecision = LayoutDecision.ACCEPT
