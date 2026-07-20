from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChapterNarrativeOutput(BaseModel):
    chapter_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=180)


class ThemeCandidateOutput(BaseModel):
    title: str = Field(min_length=2, max_length=8)
    include_concepts: list[str] = Field(default_factory=list, max_length=8)
    exclude_concepts: list[str] = Field(default_factory=list, max_length=8)
    constraints: dict = Field(default_factory=dict)
    recommended_strategy: Literal["balanced", "activity_first", "time_first", "location_first"] = "balanced"

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value):
        title = "".join(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", str(value or "")))[:8]
        if len(title) < 2:
            raise ValueError("theme title must contain 2 to 8 Chinese characters")
        return title

    @field_validator("include_concepts", "exclude_concepts", mode="before")
    @classmethod
    def trim_concepts(cls, value):
        if not isinstance(value, list):
            return value
        concepts: list[str] = []
        seen: set[str] = set()
        for item in value:
            concept = str(item or "").strip().lower()
            if concept and concept not in seen:
                concepts.append(concept)
                seen.add(concept)
            if len(concepts) == 8:
                break
        return concepts

    @field_validator("constraints", mode="before")
    @classmethod
    def normalize_constraints(cls, value):
        return value if isinstance(value, dict) else {}

    @field_validator("recommended_strategy", mode="before")
    @classmethod
    def normalize_strategy(cls, value):
        strategy = str(value or "").strip().lower()
        return strategy if strategy in {"balanced", "activity_first", "time_first", "location_first"} else "balanced"


class ThemeCandidateBatchOutput(BaseModel):
    themes: list[ThemeCandidateOutput] = Field(min_length=1, max_length=5)

    @field_validator("themes", mode="before")
    @classmethod
    def trim_themes(cls, value):
        return value[:5] if isinstance(value, list) else value


class ThemeConceptEntailmentItem(BaseModel):
    concept: str = Field(min_length=1, max_length=80)
    entailed: bool


class ThemeConceptEntailmentOutput(BaseModel):
    concepts: list[ThemeConceptEntailmentItem] = Field(default_factory=list, max_length=24)


class PhotoCaptionOutput(BaseModel):
    photo_id: str
    text: str = Field(default="", max_length=120)


class LayoutRecommendationOutput(BaseModel):
    style_key: str = Field(min_length=1, max_length=64)
    page_role: Literal["opening", "standard", "closing", "hero_spread"]
    template_key: str = Field(min_length=1, max_length=64)
    ordered_photo_ids: list[str] = Field(min_length=1)
    title: str = Field(default="", max_length=80)
    subtitle: str = Field(default="", max_length=120)
    captions: list[PhotoCaptionOutput] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    reason: str = Field(default="", max_length=240)
    alternatives: list[str] = Field(default_factory=list)

    @field_validator("style_key", "template_key", mode="before")
    @classmethod
    def strip_keys(cls, value: str) -> str:
        return str(value or "").strip()
