from __future__ import annotations

from pixelpress_backend.models.workflow_contracts import (
    GeneratedPageLayout,
    LayoutGenerationInput,
    LayoutGenerationOutput,
    PagePlan,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


"""版式生成节点。

职责:
- 消费 `state.page_plan`。
- 产出 `state.page_layouts`，供评分、渲染和导出使用。

输入:
- `state.page_plan`
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


def layout_generation_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    node_input = LayoutGenerationInput(
        album_id=state.request.album_id,
        book_size=state.request.book_size,
        style=state.request.style,
        page_plan=PagePlan.model_validate(state.page_plan),
    )
    page_layouts = [
        GeneratedPageLayout(
            page_id=page.page_id,
            template_id="tpl_single_full_bleed",
            layout_score=0.0,
            slots=[],
            text_blocks=[],
            render_hints={"background": "#FFFFFF", "bleed_mm": 3},
            placeholder=True,
        )
        for page in node_input.page_plan.planned_pages
    ]
    node_output = LayoutGenerationOutput(
        album_id=node_input.album_id,
        page_layouts=page_layouts,
        generation_summary={
            "page_count": len(node_input.page_plan.planned_pages),
            "fallback_page_count": len(node_input.page_plan.planned_pages),
        },
    )
    state.page_layouts = node_output.page_layouts
    state.metadata["generation_summary"] = node_output.generation_summary.model_dump(mode="python")
    return state
