from pydantic import ValidationError

from pixelpress_backend.graph.book_scoring_node import book_scoring_node
from pixelpress_backend.graph.layout_generation_node import layout_generation_node
from pixelpress_backend.graph.pagination_planning_node import pagination_planning_node
from pixelpress_backend.graph.photo_cleaning_node import photo_cleaning_node
from pixelpress_backend.models.workflow_contracts import (
    CleanedPhotoSet,
    LayoutDraft,
    PagePlan,
    ScoreSnapshot,
)


def test_photo_cleaning_node_emits_cleaned_photo_contract(workflow_state_factory):
    state = workflow_state_factory()

    result = photo_cleaning_node(state)

    assert isinstance(result.cleaned_photo_set, CleanedPhotoSet)
    assert result.cleaned_photo_set.album_id == "album-test"
    assert [item.photo_id for item in result.cleaned_photo_set.valid_photos] == ["p1", "p2", "p3"]


def test_planning_and_layout_nodes_emit_structured_contracts(
    workflow_state_factory,
    cleaned_photo_set_fixture,
    chapter_plan_fixture,
):
    state = workflow_state_factory(
        cleaned_photo_set=cleaned_photo_set_fixture,
        chapter_plan=chapter_plan_fixture,
    )

    planned_state = pagination_planning_node(state)
    assert isinstance(planned_state.page_plan, PagePlan)
    assert planned_state.page_plan.total_pages == 1
    assert planned_state.page_plan.planned_pages[0].chapter_id == "chapter-001"

    layout_state = layout_generation_node(planned_state)
    assert isinstance(layout_state.page_layouts, LayoutDraft)
    assert layout_state.page_layouts.page_layouts[0].page_id == "page-001"
    assert layout_state.page_layouts.page_layouts[0].template_id == "tpl_single_full_bleed"


def test_workflow_state_requires_structured_page_plan(workflow_state_factory):
    try:
        workflow_state_factory(
            cleaned_photo_set={"album_id": "album-test", "valid_photos": [], "dropped_photos": []},
            chapter_plan={"album_id": "album-test", "chapters": []},
            page_plan={"album_id": "album-test"},
            page_layouts={"album_id": "album-test", "page_layouts": []},
        )
    except ValidationError:
        return

    raise AssertionError("LayoutWorkflowState should validate required page_plan fields")


def test_book_scoring_node_emits_score_contract(
    workflow_state_factory,
    chapter_plan_fixture,
    page_plan_fixture,
    page_layouts_fixture,
):
    state = workflow_state_factory(
        cleaned_photo_set={"album_id": "album-test", "valid_photos": [], "dropped_photos": []},
        chapter_plan=chapter_plan_fixture,
        page_plan=page_plan_fixture,
        page_layouts=page_layouts_fixture,
    )

    result = book_scoring_node(state)

    assert isinstance(result.score_snapshot, ScoreSnapshot)
    assert result.score_snapshot.global_scores.overall == 0.0
    assert result.decision.value == "accept"
