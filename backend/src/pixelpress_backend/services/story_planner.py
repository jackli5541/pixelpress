from __future__ import annotations

import json
from collections import Counter
from typing import Protocol
from urllib import error, request

from pixelpress_backend.core.config import settings
from pixelpress_backend.models.common import BaseSchema
from pixelpress_backend.models.domain import GenerateConstraints

"""章节故事策划服务。

该模块负责为节点三提供“章节故事线 + 每页照片建议”的可选能力。
默认设计是：
1. 有模型配置时，调用兼容 OpenAI Chat Completions 的模型接口；
2. 模型不可用或返回异常时，自动回退到本地启发式策划器；
3. 无论使用哪种实现，输出都必须是结构化对象，供规则层继续校验和落地。
"""


class StoryPhotoSummary(BaseSchema):
    """提供给故事策划器的照片摘要。"""
    photo_id: str
    rank_weight: float = 0.0
    person_ids: list[str] = []
    scene_tags: list[str] = []
    orientation: str | None = None
    is_duplicate: bool = False
    captured_at: str | None = None


class ChapterStoryPlannerInput(BaseSchema):
    """章节故事策划器输入。"""
    album_id: str
    chapter_id: str
    title_candidate: str | None = None
    cover_photo_id: str | None = None
    page_roles: list[str] = []
    constraints: GenerateConstraints
    photo_summaries: list[StoryPhotoSummary] = []


class StoryPageSuggestion(BaseSchema):
    """单页故事建议。"""
    page_index: int
    page_role: str
    candidate_photo_ids: list[str] = []
    narrative_purpose: str | None = None
    reason: str | None = None


class ChapterStorySuggestion(BaseSchema):
    """单章节故事策划结果。"""
    chapter_id: str
    provider: str
    chapter_theme: str | None = None
    story_arc: str | None = None
    page_suggestions: list[StoryPageSuggestion] = []


class ChapterStoryPlanner(Protocol):
    """章节故事策划器协议。

    任何故事策划实现都必须遵守该协议，便于节点三在规则层上方无缝切换实现。
    """

    def plan_chapter(self, planner_input: ChapterStoryPlannerInput) -> ChapterStorySuggestion | None:
        ...


def _dedupe_keep_order(values: list[str]) -> list[str]:
    """按原顺序去重字符串列表。"""
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped


def _extract_json_object(content: str) -> dict:
    """从模型返回文本中提取 JSON 对象。

    兼容裸 JSON 和 ```json 代码块两种常见返回格式。
    """
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start_index = cleaned.find("{")
    end_index = cleaned.rfind("}")
    if start_index == -1 or end_index == -1 or start_index >= end_index:
        raise ValueError("story planner response does not contain a JSON object")
    return json.loads(cleaned[start_index : end_index + 1])


class HeuristicStoryPlanner:
    """启发式章节故事策划器。

    当未配置模型或模型请求失败时，使用本地规则生成章节主题和页级建议，
    保证节点三不会因为外部依赖异常而中断。
    """

    provider_name = "heuristic"

    def plan_chapter(self, planner_input: ChapterStoryPlannerInput) -> ChapterStorySuggestion:
        """基于章节照片摘要生成可解释的回退建议。"""
        scene_counter = Counter(tag for photo in planner_input.photo_summaries for tag in photo.scene_tags)
        top_scenes = [tag for tag, _ in scene_counter.most_common(3)]
        people = sorted({person_id for photo in planner_input.photo_summaries for person_id in photo.person_ids})
        chapter_theme_parts = [planner_input.title_candidate or "未命名章节"]
        if top_scenes:
            chapter_theme_parts.append(" / ".join(top_scenes))
        if planner_input.constraints.hero_person_id and planner_input.constraints.hero_person_id in people:
            chapter_theme_parts.append(f"主角 {planner_input.constraints.hero_person_id}")
        chapter_theme = " | ".join(chapter_theme_parts)

        sequence_ids = [photo.photo_id for photo in planner_input.photo_summaries]
        ranked_ids = [
            photo.photo_id
            for photo in sorted(
                planner_input.photo_summaries,
                key=lambda photo: (
                    1
                    if planner_input.constraints.hero_person_id
                    and planner_input.constraints.hero_person_id in photo.person_ids
                    else 0,
                    0 if not photo.is_duplicate else -1,
                    photo.rank_weight,
                ),
                reverse=True,
            )
        ]

        used_ids: set[str] = set()
        page_suggestions: list[StoryPageSuggestion] = []
        for page_index, page_role in enumerate(planner_input.page_roles):
            suggested_ids: list[str]
            if page_role == "chapter_opening":
                suggested_ids = [planner_input.cover_photo_id] if planner_input.cover_photo_id else ranked_ids[:1]
            elif page_role == "hero":
                suggested_ids = [photo_id for photo_id in ranked_ids if photo_id not in used_ids][:1]
            elif page_role == "collage":
                suggested_ids = [photo_id for photo_id in sequence_ids if photo_id not in used_ids][:2]
            elif page_role == "summary":
                suggested_ids = [photo_id for photo_id in sequence_ids if photo_id not in used_ids][:2]
            elif page_role == "ending":
                suggested_ids = [photo_id for photo_id in list(reversed(sequence_ids)) if photo_id not in used_ids][:2]
            else:
                suggested_ids = [photo_id for photo_id in sequence_ids if photo_id not in used_ids][:1]

            if not suggested_ids and sequence_ids:
                suggested_ids = sequence_ids[:1]
            suggested_ids = _dedupe_keep_order([photo_id for photo_id in suggested_ids if photo_id is not None])
            used_ids.update(suggested_ids)
            page_suggestions.append(
                StoryPageSuggestion(
                    page_index=page_index,
                    page_role=page_role,
                    candidate_photo_ids=suggested_ids,
                    narrative_purpose=f"{page_role} narrative beat",
                    reason="heuristic fallback suggestion",
                )
            )

        return ChapterStorySuggestion(
            chapter_id=planner_input.chapter_id,
            provider=self.provider_name,
            chapter_theme=chapter_theme,
            story_arc=" -> ".join(planner_input.page_roles),
            page_suggestions=page_suggestions,
        )


class OpenAICompatibleStoryPlanner:
    """兼容 OpenAI Chat Completions 的故事策划器实现。"""

    provider_name = "openai_compatible"

    def __init__(self, *, base_url: str, api_key: str | None, model_name: str, timeout_seconds: int) -> None:
        """初始化模型访问参数。"""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    def _build_messages(self, planner_input: ChapterStoryPlannerInput) -> list[dict]:
        """构建发送给模型的消息体。"""
        system_prompt = (
            "你是相册故事策划师。"
            "请根据章节照片摘要输出严格 JSON，对章节进行故事线判断，并为每页输出 page_role 和 candidate_photo_ids。"
            "必须遵守给定的页数、照片池和 must_include/must_exclude 约束，不要输出解释性文本。"
        )
        user_payload = {
            "chapter": planner_input.model_dump(mode="json"),
            "output_schema": {
                "chapter_id": "string",
                "chapter_theme": "string",
                "story_arc": "string",
                "page_suggestions": [
                    {
                        "page_index": 0,
                        "page_role": "chapter_opening|hero|transition|collage|detail|summary|ending",
                        "candidate_photo_ids": ["photo_id"],
                        "narrative_purpose": "string",
                        "reason": "string",
                    }
                ],
            },
        }
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ]

    def plan_chapter(self, planner_input: ChapterStoryPlannerInput) -> ChapterStorySuggestion | None:
        """调用模型生成章节故事建议。"""
        payload = {
            "model": self.model_name,
            "messages": self._build_messages(planner_input),
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        content = response_payload["choices"][0]["message"]["content"]
        story_payload = _extract_json_object(content)
        return ChapterStorySuggestion(
            provider=self.provider_name,
            **story_payload,
        )


class CompositeChapterStoryPlanner:
    """组合式章节故事策划器。

    先尝试主实现，失败后自动回退到兜底实现，并保持统一的输出结构。
    """

    def __init__(self, primary: ChapterStoryPlanner | None, fallback: ChapterStoryPlanner | None = None) -> None:
        """初始化主策划器与回退策划器。"""
        self.primary = primary
        self.fallback = fallback or HeuristicStoryPlanner()

    def plan_chapter(self, planner_input: ChapterStoryPlannerInput) -> ChapterStorySuggestion | None:
        """优先执行主策划器，失败时使用回退策划器。"""
        if self.primary is not None:
            try:
                suggestion = self.primary.plan_chapter(planner_input)
                if suggestion is not None:
                    return suggestion
            except (ValueError, KeyError, error.URLError, error.HTTPError, TimeoutError):
                pass
        fallback_suggestion = self.fallback.plan_chapter(planner_input)
        fallback_suggestion.provider = f"{fallback_suggestion.provider}_fallback"
        return fallback_suggestion


def get_story_planner() -> ChapterStoryPlanner | None:
    """根据当前配置创建章节故事策划器。

    返回 None 表示完全禁用模型增强，节点三将退回纯规则模式。
    """
    if settings.story_planner_enabled and settings.story_planner_provider == "openai_compatible":
        if settings.story_planner_base_url and settings.story_planner_model_name:
            primary = OpenAICompatibleStoryPlanner(
                base_url=settings.story_planner_base_url,
                api_key=settings.story_planner_api_key,
                model_name=settings.story_planner_model_name,
                timeout_seconds=settings.story_planner_timeout_seconds,
            )
            return CompositeChapterStoryPlanner(primary=primary)
        return CompositeChapterStoryPlanner(primary=None)
    return None
