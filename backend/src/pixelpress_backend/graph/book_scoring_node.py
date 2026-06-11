from __future__ import annotations
from pixelpress_backend.core.enums import LayoutDecision
from pixelpress_backend.models.workflow_contracts import (
    BookScoringInput,
    BookScoringOutput,
    BookLayoutForScoring,
    ScoreSnapshot,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


"""全书评分节点。

职责:
- 消费 `state.page_layouts`、`state.page_plan`、`state.chapter_plan`。
- 产出 `state.score_snapshot`、`state.repair_hints` 和 `state.decision`。

输入:
- `state.page_layouts`
- `state.page_plan`
- `state.chapter_plan`

输出:
- `state.score_snapshot`
- `state.repair_hints`
- `state.decision`

禁止:
- 不要直接生成新布局
- 不要修改 `state.final_layout`
- 不要无依据地总是回退到最上游

当前实现:
- 作为节点四到 finalize 的透明适配层，直接接受节点四结果
- 保留评分节点输入输出契约，方便后续替换为真实评分逻辑
"""


def book_scoring_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    book_layout = BookLayoutForScoring(
        pages=state.page_layouts or [],
        chapters=[
            {
                "chapter_id": chapter.chapter_id,
                "page_ids": [
                    page.page_id
                    for page in (state.page_plan.planned_pages if state.page_plan else [])
                    if page.chapter_id == chapter.chapter_id
                ],
            }
            for chapter in (state.chapter_plan.chapters if state.chapter_plan else [])
        ],
    )
    node_input = BookScoringInput(
        album_id=state.request.album_id,
        book_layout=book_layout,
        context={
            "hero_person_id": state.request.constraints.hero_person_id,
            "scene_mode": state.request.scene_mode,
        },
    )
    node_output = BookScoringOutput(
        album_id=node_input.album_id,
        score_snapshot=ScoreSnapshot(),
        repair_hints=[],
        decision=LayoutDecision.ACCEPT,
    )
    state.score_snapshot = node_output.score_snapshot
    state.repair_hints = node_output.repair_hints
    state.decision = node_output.decision
    state.metadata["book_scoring"] = {
        "mode": "pass_through",
        "page_count": len(node_input.book_layout.pages),
        "chapter_count": len(node_input.book_layout.chapters),
    }
    return state
