from __future__ import annotations

from pixelpress_backend.models.workflow_contracts import (
    GeneratedPageLayout,
    LayoutGenerationInput,
    LayoutGenerationOutput,
    PagePlan,
    PageSlot,
    PhotoFeature,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


"""版式生成节点。

职责:
- 消费 `state.page_plan` 和照片特征。
- 产出 `state.page_layouts`，供评分、渲染和导出使用。

输入:
- `state.page_plan`
- `state.cleaned_photo_set.valid_photos`（照片特征）
- 后续可扩展的模板 DSL、照片特征和裁切安全区

输出:
- `state.page_layouts`

禁止:
- 不要修改 `state.chapter_plan`
- 不要直接决定评分结果
- 不要写数据库或对象存储

TODO:
- 根据页面角色选择模板
- 求解槽位几何和裁切窗口
- 为文本块和渲染参数预留结构
"""


def _build_photo_features(valid_photos) -> list[PhotoFeature]:
    """从清洗后的照片构建版式生成所需的特征对象。"""
    photo_features = []
    for photo in valid_photos:
        quality_scores = {
            "overall": photo.quality_score,
            "sharpness": photo.sharpness_score,
            "exposure": photo.exposure_score,
            "blur": photo.blur_score,
            "noise": photo.noise_score,
            "face_integrity": photo.face_integrity_score,
        }
        photo_features.append(PhotoFeature(
            photo_id=photo.photo_id,
            width=photo.width,
            height=photo.height,
            face_boxes=photo.face_boxes,
            subject_boxes=photo.subject_boxes,
            embedding=photo.embedding,
            embedding_model_version=photo.embedding_model_version,
            quality_scores=quality_scores,
            scene_tags=photo.scene_tags,
            person_ids=photo.person_ids,
            perceptual_hash=photo.perceptual_hash,
            is_duplicate=photo.is_duplicate,
            orientation=photo.orientation,
        ))
    return photo_features


def _generate_slots_for_page(page, photo_features_by_id):
    """为单页生成槽位配置。"""
    slots = []
    for idx, photo_id in enumerate(page.candidate_photo_ids[:4]):
        photo_feature = photo_features_by_id.get(photo_id)
        if photo_feature:
            slot = PageSlot(
                slot_id=f"slot-{idx + 1}",
                photo_id=photo_id,
            )
            slots.append(slot)
    return slots


def layout_generation_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    valid_photos = state.cleaned_photo_set.valid_photos if state.cleaned_photo_set else []
    photo_features = _build_photo_features(valid_photos)
    photo_features_by_id = {pf.photo_id: pf for pf in photo_features}

    node_input = LayoutGenerationInput(
        album_id=state.request.album_id,
        book_size=state.request.book_size,
        style=state.request.style,
        page_plan=PagePlan.model_validate(state.page_plan),
        photo_features=photo_features,
    )

    page_layouts = []
    for page in node_input.page_plan.planned_pages:
        slots = _generate_slots_for_page(page, photo_features_by_id)
        template_id = _resolve_template(page.page_role, len(slots))

        page_layouts.append(GeneratedPageLayout(
            page_id=page.page_id,
            template_id=template_id,
            layout_score=0.0,
            slots=slots,
            text_blocks=[],
            render_hints={"background": "#FFFFFF", "bleed_mm": 3},
            placeholder=len(slots) == 0,
        ))

    fallback_count = sum(1 for pl in page_layouts if pl.placeholder)
    node_output = LayoutGenerationOutput(
        album_id=node_input.album_id,
        page_layouts=page_layouts,
        generation_summary={
            "page_count": len(node_input.page_plan.planned_pages),
            "fallback_page_count": fallback_count,
        },
    )
    state.page_layouts = node_output.page_layouts
    state.metadata["generation_summary"] = node_output.generation_summary.model_dump(mode="python")
    return state


def _resolve_template(page_role: str, slot_count: int) -> str:
    """根据页面角色和槽位数量选择模板。"""
    if page_role == "hero" and slot_count >= 1:
        return "tpl_hero_full_bleed"
    elif page_role == "collage" and slot_count >= 2:
        return "tpl_collage_2up" if slot_count == 2 else "tpl_collage_3up" if slot_count == 3 else "tpl_collage_4up"
    elif page_role == "chapter_opening":
        return "tpl_chapter_opening"
    elif page_role == "detail":
        return "tpl_single_detail"
    elif page_role == "summary":
        return "tpl_summary_grid"
    else:
        return "tpl_single_full_bleed"
