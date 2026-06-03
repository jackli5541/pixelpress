from __future__ import annotations

from pixelpress_backend.models.domain import LayoutWorkflowState


"""照片清洗节点。

职责:
- 消费 `state.request.photo_ids` 和后续可扩展的照片特征输入。
- 产出 `state.cleaned_photo_set`，供章节聚类和页面规划复用。

输入:
- `state.request`

输出:
- `state.cleaned_photo_set`

禁止:
- 不要写数据库
- 不要修改 `state.chapter_plan` / `state.page_plan` / `state.page_layouts`
- 不要直接改 `AlbumState` / `TaskState`

TODO:
- 接入质量评分、去重、极差图剔除、must_include/must_exclude 约束
- 输出统一的 `valid_photos` / `dropped_photos` 结构
"""


def photo_cleaning_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    request = state.request
    state.cleaned_photo_set = {
        "album_id": request.album_id,
        "valid_photos": [
            {
                "photo_id": photo_id,
                "decision": "keep",
                "rank_weight": 1.0,
            }
            for photo_id in request.photo_ids
        ],
        "dropped_photos": [],
    }
    return state
