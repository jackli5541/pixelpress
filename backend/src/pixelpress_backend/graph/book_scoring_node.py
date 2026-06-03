from __future__ import annotations

from pixelpress_backend.core.enums import LayoutDecision
from pixelpress_backend.models.domain import LayoutWorkflowState, RepairHint


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
- 根据问题定位输出 `accept | retry_layout | retry_planning`
"""


def book_scoring_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    state.score_snapshot = {
        "hard_violations": [],
        "soft_scores": {
            "subject_salience": 0.0,
            "page_balance": 0.0,
            "story_coherence": 0.0,
            "layout_diversity": 0.0,
            "print_safety": 0.0,
        },
        "global_scores": {
            "overall": 0.0,
        },
    }
    state.repair_hints = [RepairHint(target="pipeline", action="fill_real_logic")]
    state.decision = LayoutDecision.ACCEPT.value
    return state
