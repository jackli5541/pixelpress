from __future__ import annotations

from pixelpress_backend.models.workflow_contracts import (
    ChapterPlan,
    CleanedPhotoSet,
    PagePlan,
    PaginationPlanningInput,
    PlannedPage,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


"""页面规划节点。

职责:
- 消费 `state.chapter_plan` 和清洗后的候选照片。
- 产出 `state.page_plan`，定义章节页数预算和页面角色。

输入:
- `state.chapter_plan`
- `state.cleaned_photo_set`
- `state.request.constraints`

输出:
- `state.page_plan`

禁止:
- 不要直接生成几何坐标
- 不要写 `state.page_layouts`
- 不要修改最终布局版本

TODO:
- 决定总页数、章节页数、跨页候选、多图拼版候选和主视觉候选
- 支持主角人物曝光率、avoid_spread 等约束
"""


def pagination_planning_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    node_input = PaginationPlanningInput(
        album_id=state.request.album_id,
        constraints=state.request.constraints,
        cleaned_photo_set=CleanedPhotoSet.model_validate(state.cleaned_photo_set),
        chapter_plan=ChapterPlan.model_validate(state.chapter_plan),
    )
    chapters = node_input.chapter_plan.chapters
    first_photo = None
    if chapters and chapters[0].photo_ids:
        first_photo = chapters[0].photo_ids[0]
    page_plan = PagePlan(
        album_id=node_input.album_id,
        total_pages=max(node_input.constraints.min_pages, 1),
        planned_pages=[
            PlannedPage(
                page_id="page-001",
                chapter_id=chapters[0].chapter_id if chapters else "chapter-001",
                page_role="chapter_opening",
                candidate_photo_ids=[first_photo] if first_photo else [],
                layout_family="single_full_bleed",
                text_need="chapter_title",
            )
        ],
    )
    state.page_plan = page_plan
    return state
