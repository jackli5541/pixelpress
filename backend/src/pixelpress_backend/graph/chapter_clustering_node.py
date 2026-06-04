from __future__ import annotations

from pixelpress_backend.models.workflow_contracts import (
    ChapterClusteringInput,
    ChapterPlan,
    ChapterPlanItem,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


"""章节聚类节点。

职责:
- 消费 `state.cleaned_photo_set`。
- 产出 `state.chapter_plan`，供页面规划层使用。

输入:
- `state.cleaned_photo_set`
- `state.request.scene_mode`

输出:
- `state.chapter_plan`

禁止:
- 不要回写 `state.cleaned_photo_set`
- 不要直接生成页面级结构
- 不要改任务状态或布局版本

TODO:
- 融合时间、地点、embedding、人物、场景标签进行章节切分
- 输出章节标题候选、代表图、低置信章节标记
"""


def chapter_clustering_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    node_input = ChapterClusteringInput(
        album_id=state.request.album_id,
        scene_mode=state.request.scene_mode,
        valid_photos=state.cleaned_photo_set.valid_photos if state.cleaned_photo_set else [],
        constraints=state.request.constraints,
    )
    photo_ids = [item.photo_id for item in node_input.valid_photos]
    cover_photo_id = photo_ids[0] if photo_ids else None
    captured_times = [item.captured_at for item in node_input.valid_photos if item.captured_at is not None]
    scene_tags: list[str] = []
    key_person_ids: list[str] = []
    for item in node_input.valid_photos:
        for tag in item.scene_tags:
            if tag not in scene_tags:
                scene_tags.append(tag)
        for person_id in item.person_ids:
            if person_id not in key_person_ids:
                key_person_ids.append(person_id)
    chapter_plan = ChapterPlan(
        album_id=node_input.album_id,
        chapters=[
            ChapterPlanItem(
                chapter_id="chapter-001",
                order=1,
                title_candidate="待实现章节聚类",
                photo_ids=photo_ids,
                cover_photo_id=cover_photo_id,
                key_person_ids=key_person_ids,
                scene_tags=scene_tags,
                time_range={
                    "start": min(captured_times) if captured_times else None,
                    "end": max(captured_times) if captured_times else None,
                },
                cluster_confidence=1.0 if photo_ids else 0.0,
            )
        ],
        clustering_summary={
            "chapter_count": 1 if photo_ids else 0,
            "avg_photos_per_chapter": len(photo_ids) if photo_ids else 0,
            "low_confidence_chapters": [],
        },
    )
    state.chapter_plan = chapter_plan
    return state
