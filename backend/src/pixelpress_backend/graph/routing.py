from __future__ import annotations

from pixelpress_backend.core.enums import LayoutDecision
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def score_router(state: LayoutWorkflowState) -> str:
    if state.decision is None:
        return LayoutDecision.ACCEPT.value
    return state.decision.value
