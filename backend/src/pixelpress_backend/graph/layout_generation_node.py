"""版式生成节点。

职责:
- 消费 `state.page_plan` + `state.request.photo_assets` + `state.cleaned_photo_set`。
- 通过 Template Compatibility Scorer（8 因子加权评分）为每页选出最佳模板。
- 产出 `state.page_layouts`，供评分、渲染和导出使用。

输入:
- `state.page_plan`（来自 Node3）
- `state.request.photo_assets`（照片宽高）
- `state.cleaned_photo_set`（有效照片 ID 列表）
- `state.request.style` / `state.request.book_size`（上下文）

输出:
- `state.page_layouts`（含 template_id、layout_score、slots、text_blocks 等）
- `state.metadata["generation_summary"]`（含 page_count、fallback_page_count）

禁止:
- 不要修改 `state.chapter_plan` 或 `state.page_plan`
- 不要直接决定评分结果
- 不要写数据库或对象存储

TODO:
- 求解槽位几何和裁切窗口
- 为文本块和渲染参数预留结构
"""

from __future__ import annotations

from pixelpress_backend.algorithms.layout_templates import (
    TEMPLATE_REGISTRY,
    select_best_template,
)
from pixelpress_backend.models.workflow_contracts import (
    GeneratedPageLayout,
    GenerationSummary,
    LayoutGenerationInput,
    LayoutGenerationOutput,
    PagePlan,
    PhotoFeature,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def layout_generation_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    """版式生成主节点。

    为 page_plan 中每个页面独立选择模板，产出 GeneratedPageLayout 列表。
    模板选择由 8 因子 Compatibility Scorer 驱动，argmax 选最优。
    低分页面自动兜底 tpl_single_full_bleed。
    """
    node_input = LayoutGenerationInput(
        album_id=state.request.album_id,
        book_size=state.request.book_size,
        style=state.request.style,
        page_plan=PagePlan.model_validate(state.page_plan),
    )

    # 构建 PhotoFeature 列表（从 request.photo_assets 取宽高）
    pf_map = _build_photo_feature_map(state)

    # 上下文：跟踪已选模板家族用于多样性约束
    prev_families: list[str] = []
    album_type = _resolve_album_type(state)

    page_layouts: list[GeneratedPageLayout] = []
    fallback_count = 0

    for page in node_input.page_plan.planned_pages:
        # 收集该页候选照片的 PhotoFeature
        photos = _resolve_candidate_photos(page.candidate_photo_ids, pf_map)

        # 构建评分上下文
        context = {
            "page_role": page.page_role,
            "album_type": album_type,
            "prev_template_ids": list(prev_families),
            "style": state.request.style,
        }

        # 选择最佳模板
        all_templates = list(TEMPLATE_REGISTRY.values())
        best_template, compat_score = select_best_template(all_templates, photos, context)

        # 判断是否为兜底（分数过低且精确命中 full_bleed）
        is_fallback = best_template.template_id == "tpl_single_full_bleed" and compat_score < 0.3
        if is_fallback:
            fallback_count += 1

        # 记录模板家族（用于多样性）
        prev_families.append(best_template.layout_family)

        page_layouts.append(
            GeneratedPageLayout(
                page_id=page.page_id,
                template_id=best_template.template_id,
                layout_score=compat_score,
                slots=[],          # TODO: 槽位几何求解
                text_blocks=[],    # TODO: 文本块生成
                render_hints={
                    "background": "#FFFFFF",
                    "bleed_mm": 3,
                    "layout_family": best_template.layout_family,
                    "decoration_mode": best_template.decoration_mode,
                },
                placeholder=is_fallback,
            )
        )

    node_output = LayoutGenerationOutput(
        album_id=node_input.album_id,
        page_layouts=page_layouts,
        generation_summary=GenerationSummary(
            page_count=len(page_layouts),
            fallback_page_count=fallback_count,
        ),
    )

    state.page_layouts = node_output.page_layouts
    state.metadata["generation_summary"] = node_output.generation_summary.model_dump(mode="python")
    return state


def _build_photo_feature_map(state: LayoutWorkflowState) -> dict[str, PhotoFeature]:
    """从 request.photo_assets 构建 photo_id → PhotoFeature 映射。

    PhotoFeature 包含 width/height，供朝向分类和 DPI 估算使用。
    后续 Phase 可扩展 face_boxes、subject_boxes 等字段。
    """
    asset_map = {a.photo_id: a for a in state.request.photo_assets}

    # 确定哪些 photo_id 在有效照片集中
    valid_ids: set[str] = set()
    if state.cleaned_photo_set:
        valid_ids = {p.photo_id for p in state.cleaned_photo_set.valid_photos}

    features: dict[str, PhotoFeature] = {}
    for photo_id, asset in asset_map.items():
        if valid_ids and photo_id not in valid_ids:
            continue
        features[photo_id] = PhotoFeature(
            photo_id=photo_id,
            width=asset.width,
            height=asset.height,
        )
    return features


def _resolve_candidate_photos(
    candidate_ids: list[str],
    pf_map: dict[str, PhotoFeature],
) -> list[PhotoFeature]:
    """解析 candidate_photo_ids 为 PhotoFeature 列表。

    找不到特征的照片会被静默跳过。
    """
    return [pf_map[pid] for pid in candidate_ids if pid in pf_map]


def _resolve_album_type(state: LayoutWorkflowState) -> str:
    """从 SceneMode 推导 album_type 字符串。

    当前只有 annual/event 两种场景模式，映射为通用 album_type。
    未来可扩展为更细粒度（wedding/graduation/family/travel）。
    """
    mode = state.request.scene_mode.value if state.request.scene_mode else "annual"
    return "universal"
