from __future__ import annotations

from pixelpress_backend.core.enums import LayoutDecision
from pixelpress_backend.graph.book_scoring_node import book_scoring_node
from pixelpress_backend.graph.chapter_clustering_node import chapter_clustering_node
from pixelpress_backend.graph.layout_generation_node import layout_generation_node
from pixelpress_backend.graph.pagination_planning_node import pagination_planning_node
from pixelpress_backend.graph.photo_cleaning_node import photo_cleaning_node
from pixelpress_backend.models.domain import BookLayout
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def finalize_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    next_version = 1 if state.request.base_version is None else state.request.base_version + 1
    state.final_layout = BookLayout(
        album_id=state.request.album_id,
        version=next_version,
        base_version=state.request.base_version,
        pages=state.page_layouts.model_dump(mode="python")["page_layouts"] if state.page_layouts else [],
        chapters=state.chapter_plan.model_dump(mode="python")["chapters"] if state.chapter_plan else [],
        score_snapshot=state.score_snapshot.model_dump(mode="python"),
        generation_meta={
            "pipeline_version": "0.1.0",
            "input_hash": f"{state.request.album_id}:{len(state.request.photo_ids)}",
        },
        render_snapshot={
            "render_engine_version": "placeholder",
            "font_pack_version": "placeholder",
            "color_profile": "sRGB-preview",
            "thumbnail_profile": "default",
        },
        export_snapshot={
            "pdf_profile_version": "placeholder",
            "bleed_mm": 3,
            "safe_margin_mm": 5,
            "font_embed_mode": "subset",
            "image_sampling_policy": "placeholder",
        },
    )
    return state


def score_router(state: LayoutWorkflowState) -> str:
    if state.decision is None:
        return LayoutDecision.ACCEPT.value
    return state.decision.value
