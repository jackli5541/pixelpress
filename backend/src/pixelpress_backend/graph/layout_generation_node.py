from __future__ import annotations

from pixelpress_backend.models.domain import LayoutWorkflowState


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
    planned_pages = state.page_plan.get("planned_pages", [])
    state.page_layouts = {
        "album_id": state.request.album_id,
        "page_layouts": [
            {
                "page_id": page["page_id"],
                "template_id": "tpl_single_full_bleed",
                "layout_score": 0.0,
                "slots": [],
                "text_blocks": [],
                "placeholder": True,
            }
            for page in planned_pages
        ],
    }
    return state
