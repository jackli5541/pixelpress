from __future__ import annotations

from pixelpress_backend.models.domain import RepairHint
from pixelpress_backend.models.workflow_contracts import (
    BookScoringInput,
    BookScoringOutput,
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

TODO:
- 实现硬规则检查、软评分计算、全书节奏评估
- 根据问题定位输出 `accept | retry_layout | retry_planning | retry_chapter_clustering`
"""


def book_scoring_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    book_layout = {
        "pages": state.page_layouts or [],
        "chapters": [
            {
                "chapter_id": chapter.chapter_id,
                "page_ids": [
                    page.page_id for page in (state.page_plan.planned_pages if state.page_plan else []) if page.chapter_id == chapter.chapter_id
                ],
            }
            for chapter in (state.chapter_plan.chapters if state.chapter_plan else [])
        ],
    }
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
        repair_hints=[RepairHint(target="pipeline", action="fill_real_logic")],
    )
    state.score_snapshot = node_output.score_snapshot
    state.repair_hints = node_output.repair_hints
    state.decision = node_output.decision
    return state
