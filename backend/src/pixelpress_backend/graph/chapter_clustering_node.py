from __future__ import annotations

from pixelpress_backend.models.workflow_contracts import (
    ChapterClusteringInput,
    ChapterPlan,
    ChapterPlanItem,
    CleanedPhotoSet,
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
        cleaned_photo_set=CleanedPhotoSet.model_validate(state.cleaned_photo_set),
    )
    photo_ids = [item.photo_id for item in node_input.cleaned_photo_set.valid_photos]
    chapter_plan = ChapterPlan(
        album_id=node_input.album_id,
        chapters=[
            ChapterPlanItem(
                chapter_id="chapter-001",
                order=1,
                title_candidate="待实现章节聚类",
                photo_ids=photo_ids,
            )
        ],
    )
    state.chapter_plan = chapter_plan
    return state
