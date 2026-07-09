from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChapterItemOutput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=180)
    photo_ids: list[str] = Field(min_length=1)


class ChapterClusterOutput(BaseModel):
    chapters: list[ChapterItemOutput] = Field(min_length=1)


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
