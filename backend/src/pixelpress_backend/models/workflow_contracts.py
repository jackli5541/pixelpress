from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from pixelpress_backend.core.enums import LayoutDecision, SceneMode
from pixelpress_backend.models.common import BaseSchema, JSONDict
from pixelpress_backend.models.domain import (
    GenerateConstraints,
    PhotoAsset,
    RelativeFrame,
    RepairHint,
)


class KeptPhoto(BaseSchema):
    photo_id: str
    decision: Literal["keep", "deprioritize", "drop"] = "keep"
    rank_weight: float = 1.0
    quality_score: float | None = None
    duplicate_score: float | None = None
    saliency_score: float | None = None
    face_integrity_score: float | None = None
    drop_reason: str | None = None
    captured_at: datetime | None = None
    location_cluster: str | None = None
    embedding_ref: str | None = None
    person_ids: list[str] = Field(default_factory=list)
    scene_tags: list[str] = Field(default_factory=list)
    orientation: str | None = None
    is_duplicate: bool = False


class DroppedPhoto(BaseSchema):
    photo_id: str
    reason: str = "filtered"


class CleaningSummary(BaseSchema):
    input_count: int = 0
    valid_count: int = 0
    dropped_count: int = 0
    duplicate_groups: int = 0


class CleanedPhotoSet(BaseSchema):
    album_id: str
    valid_photos: list[KeptPhoto] = Field(default_factory=list)
    dropped_photos: list[DroppedPhoto] = Field(default_factory=list)
    cleaning_summary: CleaningSummary = Field(default_factory=CleaningSummary)


class PhotoCleaningInput(BaseSchema):
    album_id: str
    scene_mode: SceneMode
    book_size: str
    photo_assets: list[PhotoAsset] = Field(default_factory=list)
    constraints: GenerateConstraints = Field(default_factory=GenerateConstraints)


class PhotoCleaningOutput(CleanedPhotoSet):
    pass


class TimeRange(BaseSchema):
    start: datetime | None = None
    end: datetime | None = None


class ChapterPlanItem(BaseSchema):
    chapter_id: str
    order: int
    title_candidate: str
    photo_ids: list[str] = Field(default_factory=list)
    cover_photo_id: str | None = None
    key_person_ids: list[str] = Field(default_factory=list)
    scene_tags: list[str] = Field(default_factory=list)
    time_range: TimeRange = Field(default_factory=TimeRange)
    cluster_confidence: float | None = None


class ClusteringSummary(BaseSchema):
    chapter_count: int = 0
    avg_photos_per_chapter: int = 0
    low_confidence_chapters: list[str] = Field(default_factory=list)


class ChapterPlan(BaseSchema):
    album_id: str
    chapters: list[ChapterPlanItem] = Field(default_factory=list)
    clustering_summary: ClusteringSummary = Field(default_factory=ClusteringSummary)


class ChapterClusteringInput(BaseSchema):
    album_id: str
    scene_mode: SceneMode
    valid_photos: list[KeptPhoto] = Field(default_factory=list)
    constraints: GenerateConstraints = Field(default_factory=GenerateConstraints)


class ChapterClusteringOutput(ChapterPlan):
    pass


class ChapterPageBudget(BaseSchema):
    chapter_id: str
    start_page: int
    end_page: int
    page_count: int


class PlannedPage(BaseSchema):
    page_id: str
    chapter_id: str
    page_role: str
    candidate_photo_ids: list[str] = Field(default_factory=list)
    layout_family: str
    is_spread: bool = False
    text_need: str


class PlanningSummary(BaseSchema):
    selected_photo_count: int = 0
    unused_photo_count: int = 0
    spread_count: int = 0


class PagePlan(BaseSchema):
    total_pages: int
    chapter_page_budgets: list[ChapterPageBudget] = Field(default_factory=list)
    planned_pages: list[PlannedPage] = Field(default_factory=list)


class PaginationPlanningInput(BaseSchema):
    album_id: str
    book_size: str = "A4_square"
    binding: str = "hardcover"
    style: str = "minimal"
    constraints: GenerateConstraints
    chapters: list[ChapterPlanItem] = Field(default_factory=list)
    photo_pool: list[KeptPhoto] = Field(default_factory=list)


class PaginationPlanningOutput(BaseSchema):
    album_id: str
    page_plan: PagePlan
    planning_summary: PlanningSummary = Field(default_factory=PlanningSummary)


class LayoutTemplate(BaseSchema):
    template_id: str
    family: str
    slot_count: int


class PhotoFeature(BaseSchema):
    photo_id: str
    width: int | None = None
    height: int | None = None
    face_boxes: list[RelativeFrame] = Field(default_factory=list)
    subject_boxes: list[RelativeFrame] = Field(default_factory=list)
    safe_crop_window: RelativeFrame | None = None


class PageSlot(BaseSchema):
    slot_id: str
    photo_id: str | None = None
    frame: RelativeFrame = Field(default_factory=RelativeFrame)
    crop: RelativeFrame | None = None


class TextBlock(BaseSchema):
    block_id: str
    type: str
    frame: RelativeFrame = Field(default_factory=RelativeFrame)


class GeneratedPageLayout(BaseSchema):
    page_id: str
    template_id: str
    layout_score: float = 0.0
    slots: list[PageSlot] = Field(default_factory=list)
    text_blocks: list[TextBlock] = Field(default_factory=list)
    render_hints: JSONDict = Field(default_factory=dict)
    placeholder: bool = True


class GenerationSummary(BaseSchema):
    page_count: int = 0
    fallback_page_count: int = 0


class LayoutGenerationInput(BaseSchema):
    album_id: str
    book_size: str = "A4_square"
    style: str = "minimal"
    page_plan: PagePlan
    layout_templates: list[LayoutTemplate] = Field(default_factory=list)
    photo_features: list[PhotoFeature] = Field(default_factory=list)


class LayoutGenerationOutput(BaseSchema):
    album_id: str
    page_layouts: list[GeneratedPageLayout] = Field(default_factory=list)
    generation_summary: GenerationSummary = Field(default_factory=GenerationSummary)


class HardViolation(BaseSchema):
    page_id: str
    rule: str
    severity: str


class SoftScoreSnapshot(BaseSchema):
    subject_salience: float = 0.0
    page_balance: float = 0.0
    story_coherence: float = 0.0
    layout_diversity: float = 0.0
    print_safety: float = 0.0


class GlobalScoreSnapshot(BaseSchema):
    overall: float = 0.0
    chapter_rhythm: float = 0.0
    hero_exposure: float = 0.0


class ScoreSnapshot(BaseSchema):
    hard_violations: list[HardViolation] = Field(default_factory=list)
    soft_scores: SoftScoreSnapshot = Field(default_factory=SoftScoreSnapshot)
    global_scores: GlobalScoreSnapshot = Field(default_factory=GlobalScoreSnapshot)


class BookLayoutForScoring(BaseSchema):
    pages: list[GeneratedPageLayout] = Field(default_factory=list)
    chapters: list[JSONDict] = Field(default_factory=list)


class ScoringContext(BaseSchema):
    hero_person_id: str | None = None
    scene_mode: SceneMode | None = None


class ScoringRules(BaseSchema):
    hard_rules_enabled: bool = True
    soft_weights: JSONDict = Field(default_factory=dict)


class BookScoringInput(BaseSchema):
    album_id: str
    book_layout: BookLayoutForScoring
    scoring_rules: ScoringRules = Field(default_factory=ScoringRules)
    context: ScoringContext = Field(default_factory=ScoringContext)


class BookScoringOutput(BaseSchema):
    album_id: str
    score_snapshot: ScoreSnapshot
    repair_hints: list[RepairHint] = Field(default_factory=list)
    decision: LayoutDecision = LayoutDecision.ACCEPT
