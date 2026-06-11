from __future__ import annotations

import hashlib
import json

from pixelpress_backend.models.domain import BookLayout
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def _build_input_hash(state: LayoutWorkflowState) -> str:
    request_payload = {
        "album_id": state.request.album_id,
        "photo_ids": state.request.photo_ids,
        "scene_mode": state.request.scene_mode,
        "book_size": state.request.book_size,
        "binding": state.request.binding,
        "style": state.request.style,
        "constraints": state.request.constraints.model_dump(mode="python"),
        "base_version": state.request.base_version,
    }
    encoded = json.dumps(request_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def finalize_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    next_version = 1 if state.request.base_version is None else state.request.base_version + 1
    state.final_layout = BookLayout(
        album_id=state.request.album_id,
        version=next_version,
        base_version=state.request.base_version,
        pages=[page.model_dump(mode="python") for page in state.page_layouts] if state.page_layouts else [],
        chapters=state.chapter_plan.model_dump(mode="python")["chapters"] if state.chapter_plan else [],
        score_snapshot=state.score_snapshot.model_dump(mode="python"),
        generation_meta={
            "seed": state.metadata.get("seed", 0),
            "pipeline_version": "0.1.0",
            "model_versions": {
                "photo_cleaning": "placeholder",
                "chapter_clustering": "placeholder",
                "pagination_planning": "placeholder",
                "layout_generation": "placeholder",
                "book_scoring": "placeholder",
            },
            "input_hash": _build_input_hash(state),
        },
        render_snapshot={
            "render_engine_version": "placeholder",
            "font_pack_version": "placeholder",
            "page_size": state.request.book_size,
            "bleed_mm": 3,
            "safe_margin_mm": 5,
            "color_profile": "sRGB-preview",
            "page_order": [page.page_id for page in state.page_layouts] if state.page_layouts else [],
            "thumbnail_profile": "default",
        },
        export_snapshot={
            "pdf_profile_version": "placeholder",
            "page_size": state.request.book_size,
            "bleed_mm": 3,
            "safe_margin_mm": 5,
            "font_pack_version": "placeholder",
            "color_space_strategy": "CMYK-placeholder",
            "font_embed_mode": "subset",
            "page_order": [page.page_id for page in state.page_layouts] if state.page_layouts else [],
            "image_sampling_policy": "placeholder",
            "compression_policy": "placeholder",
            "render_engine_version": "placeholder",
        },
    )
    return state
