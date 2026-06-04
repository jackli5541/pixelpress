from __future__ import annotations

from pixelpress_backend.models.workflow_contracts import (
    CleanedPhotoSet,
    KeptPhoto,
    PhotoCleaningInput,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


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
    node_input = PhotoCleaningInput(
        album_id=state.request.album_id,
        scene_mode=state.request.scene_mode,
        book_size=state.request.book_size,
        photo_assets=state.request.photo_assets,
        constraints=state.request.constraints,
    )
    asset_lookup = {asset.photo_id: asset for asset in node_input.photo_assets}
    ordered_photo_ids = state.request.photo_ids if state.request.photo_ids else [asset.photo_id for asset in node_input.photo_assets]
    cleaned_photo_set = CleanedPhotoSet(
        album_id=node_input.album_id,
        valid_photos=[
            KeptPhoto(
                photo_id=photo_id,
                decision="keep",
                rank_weight=1.0,
                captured_at=asset_lookup.get(photo_id).exif.captured_at if photo_id in asset_lookup else None,
                embedding_ref=asset_lookup.get(photo_id).features.embedding if photo_id in asset_lookup else None,
                orientation=asset_lookup.get(photo_id).orientation if photo_id in asset_lookup else None,
            )
            for photo_id in ordered_photo_ids
        ],
        cleaning_summary={
            "input_count": len(ordered_photo_ids),
            "valid_count": len(ordered_photo_ids),
            "dropped_count": 0,
            "duplicate_groups": 0,
        },
    )
    state.cleaned_photo_set = cleaned_photo_set
    return state
