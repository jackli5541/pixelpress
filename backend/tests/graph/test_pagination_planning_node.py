"""分页规划节点测试。

该文件用于独立验证 `pagination_planning_node` 的核心规则、约束处理、
故事策划器接入以及测试产物落盘能力。
"""

import pytest

from pixelpress_backend.graph.pagination_planning_node import pagination_planning_node
from pixelpress_backend.models.domain import GenerateConstraints
from pixelpress_backend.models.workflow_contracts import PagePlan
from pixelpress_backend.services import story_planner as story_planner_service


@pytest.fixture(autouse=True)
def disable_story_planner_by_default(monkeypatch):
    """默认关闭故事策划器，避免真实环境变量影响规则测试。"""
    monkeypatch.setattr(story_planner_service, "get_story_planner", lambda: None)


def _save_planning_output_snapshot(json_artifact_writer, artifact_name: str, result) -> None:
    """将节点输出保存为 JSON，便于人工审阅分页结果。"""
    payload = {
        "request": result.request.model_dump(mode="json"),
        "cleaned_photo_set": result.cleaned_photo_set.model_dump(mode="json") if result.cleaned_photo_set else None,
        "chapter_plan": result.chapter_plan.model_dump(mode="json") if result.chapter_plan else None,
        "page_plan": result.page_plan.model_dump(mode="json") if result.page_plan else None,
        "planning_summary": result.metadata.get("planning_summary"),
        "planning_debug": result.metadata.get("planning_debug"),
        "story_planner": result.metadata.get("story_planner"),
    }
    json_artifact_writer(f"graph/pagination_planning/{artifact_name}.json", payload)


def test_pagination_planning_node_builds_multi_page_plan(
    workflow_state_factory,
    cleaned_photo_set_fixture,
    json_artifact_writer,
):
    """验证基础多章节输入能够生成完整页计划并输出调试快照。"""
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "photo_ids": ["p1", "p2"],
            },
            {
                "chapter_id": "chapter-002",
                "order": 2,
                "title_candidate": "第二章",
                "photo_ids": ["p3"],
            },
        ],
    }

    state = workflow_state_factory(
        cleaned_photo_set=cleaned_photo_set_fixture,
        chapter_plan=chapter_plan,
    )

    result = pagination_planning_node(state)
    _save_planning_output_snapshot(json_artifact_writer, "basic_multi_page_plan", result)

    assert isinstance(result.page_plan, PagePlan)
    assert result.page_plan.total_pages == len(result.page_plan.planned_pages)
    assert result.page_plan.total_pages == 3
    assert [budget.model_dump(mode="python") for budget in result.page_plan.chapter_page_budgets] == [
        {"chapter_id": "chapter-001", "start_page": 1, "end_page": 2, "page_count": 2},
        {"chapter_id": "chapter-002", "start_page": 3, "end_page": 3, "page_count": 1},
    ]
    assert [page.page_role for page in result.page_plan.planned_pages] == [
        "chapter_opening",
        "hero",
        "chapter_opening",
    ]
    assert result.metadata["planning_summary"] == {
        "selected_photo_count": 3,
        "unused_photo_count": 0,
        "spread_count": 0,
    }


def test_pagination_planning_node_respects_fixed_page_limit(
    workflow_state_factory,
    cleaned_photo_set_fixture,
):
    """验证固定页数约束会覆盖默认页数估算结果。"""
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "photo_ids": ["p1", "p2", "p3"],
            }
        ],
    }

    state = workflow_state_factory(
        cleaned_photo_set=cleaned_photo_set_fixture,
        chapter_plan=chapter_plan,
    )
    state.request.constraints = GenerateConstraints(min_pages=3, max_pages=3)

    result = pagination_planning_node(state)

    assert result.page_plan.total_pages == 3
    assert [page.page_role for page in result.page_plan.planned_pages] == [
        "chapter_opening",
        "hero",
        "ending",
    ]


def test_pagination_planning_node_excludes_forbidden_photos(
    workflow_state_factory,
    cleaned_photo_set_fixture,
):
    """验证 must_exclude 中的照片不会进入任何页面候选。"""
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "photo_ids": ["p1", "p2", "p3"],
            }
        ],
    }

    state = workflow_state_factory(
        cleaned_photo_set=cleaned_photo_set_fixture,
        chapter_plan=chapter_plan,
    )
    state.request.constraints = GenerateConstraints(min_pages=2, max_pages=2, must_exclude=["p1"])

    result = pagination_planning_node(state)

    planned_photo_ids = [photo_id for page in result.page_plan.planned_pages for photo_id in page.candidate_photo_ids]
    assert "p1" not in planned_photo_ids


def test_pagination_planning_node_prioritizes_must_include_for_opening(
    workflow_state_factory,
    cleaned_photo_set_fixture,
):
    """验证 must_include 照片会优先进入章节首页。"""
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "photo_ids": ["p1", "p2", "p3"],
            }
        ],
    }

    state = workflow_state_factory(
        cleaned_photo_set=cleaned_photo_set_fixture,
        chapter_plan=chapter_plan,
    )
    state.request.constraints = GenerateConstraints(min_pages=2, max_pages=2, must_include=["p3"])

    result = pagination_planning_node(state)

    assert result.page_plan.planned_pages[0].candidate_photo_ids == ["p3"]


def test_pagination_planning_node_prefers_cover_photo_for_opening(
    workflow_state_factory,
    cleaned_photo_set_fixture,
):
    """验证章节封面图会优先作为章节首页候选。"""
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "photo_ids": ["p1", "p2", "p3"],
                "cover_photo_id": "p2",
            }
        ],
    }

    state = workflow_state_factory(
        cleaned_photo_set=cleaned_photo_set_fixture,
        chapter_plan=chapter_plan,
    )
    state.request.constraints = GenerateConstraints(min_pages=2, max_pages=2)

    result = pagination_planning_node(state)

    assert result.page_plan.planned_pages[0].candidate_photo_ids == ["p2"]


def test_pagination_planning_node_prefers_high_rank_photo_for_opening(
    workflow_state_factory,
):
    """验证高 rank_weight 照片会优先成为章节首页主图。"""
    cleaned_photo_set = {
        "album_id": "album-test",
        "valid_photos": [
            {"photo_id": "p_low", "decision": "keep", "rank_weight": 0.1},
            {"photo_id": "p_high", "decision": "keep", "rank_weight": 0.9},
            {"photo_id": "p_mid", "decision": "keep", "rank_weight": 0.5},
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "photo_ids": ["p_low", "p_high", "p_mid"],
            }
        ],
    }

    state = workflow_state_factory(
        cleaned_photo_set=cleaned_photo_set,
        chapter_plan=chapter_plan,
    )
    state.request.constraints = GenerateConstraints(min_pages=2, max_pages=2)

    result = pagination_planning_node(state)

    assert result.page_plan.planned_pages[0].candidate_photo_ids == ["p_high"]


def test_pagination_planning_node_prefers_hero_person_and_enables_spread_hero(
    workflow_state_factory,
):
    """验证主角人物照片会优先进入 hero 页，并在合适时触发跨页。"""
    cleaned_photo_set = {
        "album_id": "album-test",
        "valid_photos": [
            {
                "photo_id": "p1",
                "decision": "keep",
                "rank_weight": 0.95,
                "orientation": "landscape",
                "person_ids": ["hero-001"],
                "is_duplicate": False,
            },
            {
                "photo_id": "p2",
                "decision": "keep",
                "rank_weight": 0.6,
                "orientation": "portrait",
                "person_ids": [],
                "is_duplicate": False,
            },
            {
                "photo_id": "p3",
                "decision": "keep",
                "rank_weight": 0.5,
                "orientation": "portrait",
                "person_ids": [],
                "is_duplicate": False,
            },
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "cover_photo_id": "p2",
                "photo_ids": ["p2", "p1", "p3"],
            }
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(
        min_pages=2,
        max_pages=2,
        hero_person_id="hero-001",
    )

    result = pagination_planning_node(state)

    assert result.page_plan.planned_pages[0].candidate_photo_ids == ["p2"]
    assert result.page_plan.planned_pages[1].is_spread is True
    assert result.page_plan.planned_pages[1].layout_family == "spread_full_bleed"
    assert result.page_plan.planned_pages[1].candidate_photo_ids == ["p1"]


def test_pagination_planning_node_respects_avoid_spread_constraint(
    workflow_state_factory,
):
    """验证 avoid_spread 约束会禁止 hero 页输出跨页版式。"""
    cleaned_photo_set = {
        "album_id": "album-test",
        "valid_photos": [
            {
                "photo_id": "p1",
                "decision": "keep",
                "rank_weight": 0.95,
                "orientation": "landscape",
                "person_ids": [],
                "is_duplicate": False,
            },
            {
                "photo_id": "p2",
                "decision": "keep",
                "rank_weight": 0.7,
                "orientation": "portrait",
                "person_ids": [],
                "is_duplicate": False,
            },
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "photo_ids": ["p1", "p2"],
            }
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(min_pages=2, max_pages=2, avoid_spread=True)

    result = pagination_planning_node(state)

    assert result.page_plan.planned_pages[1].is_spread is False
    assert result.page_plan.planned_pages[1].layout_family == "single_full_bleed"


def test_pagination_planning_node_groups_collage_photos_by_story_sequence(
    workflow_state_factory,
):
    """验证 collage 页会按叙事顺序与场景相近度分组取图。"""
    cleaned_photo_set = {
        "album_id": "album-test",
        "valid_photos": [
            {
                "photo_id": "p1",
                "decision": "keep",
                "rank_weight": 0.7,
                "captured_at": "2026-05-01T10:00:00Z",
                "scene_tags": ["beach"],
            },
            {
                "photo_id": "p2",
                "decision": "keep",
                "rank_weight": 0.6,
                "captured_at": "2026-05-01T10:02:00Z",
                "scene_tags": ["beach"],
            },
            {
                "photo_id": "p3",
                "decision": "keep",
                "rank_weight": 0.55,
                "captured_at": "2026-05-01T10:03:00Z",
                "scene_tags": ["beach"],
            },
            {
                "photo_id": "p4",
                "decision": "keep",
                "rank_weight": 0.5,
                "captured_at": "2026-05-01T10:30:00Z",
                "scene_tags": ["street"],
            },
            {
                "photo_id": "p5",
                "decision": "keep",
                "rank_weight": 0.95,
                "captured_at": "2026-05-01T10:40:00Z",
                "scene_tags": ["street"],
            },
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "cover_photo_id": "p1",
                "photo_ids": ["p1", "p2", "p3", "p4", "p5"],
            }
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(min_pages=4, max_pages=4)

    result = pagination_planning_node(state)

    assert [page.page_role for page in result.page_plan.planned_pages] == [
        "chapter_opening",
        "hero",
        "collage",
        "ending",
    ]
    assert result.page_plan.planned_pages[0].candidate_photo_ids == ["p1"]
    assert result.page_plan.planned_pages[1].candidate_photo_ids == ["p5"]
    assert result.page_plan.planned_pages[2].candidate_photo_ids == ["p2", "p3"]
    assert "p5" not in result.page_plan.planned_pages[2].candidate_photo_ids


def test_pagination_planning_node_avoids_adjacent_page_photo_reuse_when_unique_photos_exist(
    workflow_state_factory,
):
    """验证照片充足时，相邻页面会尽量避免复用相同照片。"""
    cleaned_photo_set = {
        "album_id": "album-test",
        "valid_photos": [
            {"photo_id": "p1", "decision": "keep", "rank_weight": 0.9},
            {"photo_id": "p2", "decision": "keep", "rank_weight": 0.8},
            {"photo_id": "p3", "decision": "keep", "rank_weight": 0.7},
            {"photo_id": "p4", "decision": "keep", "rank_weight": 0.6},
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "photo_ids": ["p1", "p2", "p3", "p4"],
            }
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(min_pages=3, max_pages=3)

    result = pagination_planning_node(state)

    pages = result.page_plan.planned_pages
    assert set(pages[0].candidate_photo_ids).isdisjoint(pages[1].candidate_photo_ids)
    assert set(pages[1].candidate_photo_ids).isdisjoint(pages[2].candidate_photo_ids)


def test_pagination_planning_node_alternates_collage_layout_families(
    workflow_state_factory,
):
    """验证多个 collage 页会交替输出不同版式族，避免连续同构。"""
    cleaned_photo_set = {
        "album_id": "album-test",
        "valid_photos": [
            {"photo_id": "p1", "decision": "keep", "rank_weight": 0.7},
            {"photo_id": "p2", "decision": "keep", "rank_weight": 0.65},
            {"photo_id": "p3", "decision": "keep", "rank_weight": 0.6},
            {"photo_id": "p4", "decision": "keep", "rank_weight": 0.55},
            {"photo_id": "p5", "decision": "keep", "rank_weight": 0.5},
            {"photo_id": "p6", "decision": "keep", "rank_weight": 0.95},
            {"photo_id": "p7", "decision": "keep", "rank_weight": 0.45},
            {"photo_id": "p8", "decision": "keep", "rank_weight": 0.4},
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "第一章",
                "cover_photo_id": "p1",
                "photo_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"],
            }
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(min_pages=8, max_pages=8)

    result = pagination_planning_node(state)

    collage_pages = [page for page in result.page_plan.planned_pages if page.page_role == "collage"]
    assert len(collage_pages) == 2
    assert collage_pages[0].layout_family == "grid_nine"
    assert collage_pages[1].layout_family == "triple_narrative"


def test_pagination_planning_node_builds_extended_story_roles_for_long_chapter(
    workflow_state_factory,
    json_artifact_writer,
):
    """验证长章节会生成更完整的角色链路并保存结果快照。"""
    cleaned_photo_set = {
        "album_id": "album-test",
        "valid_photos": [
            {
                "photo_id": f"p{i}",
                "decision": "keep",
                "rank_weight": 0.95 - (i * 0.05),
                "scene_tags": ["park"] if i < 4 else ["cafe"],
                "person_ids": ["hero-001"] if i in {1, 2, 6} else [],
            }
            for i in range(1, 9)
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-test",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "长章节",
                "cover_photo_id": "p1",
                "photo_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"],
            }
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(min_pages=7, max_pages=7, hero_person_id="hero-001")

    result = pagination_planning_node(state)
    _save_planning_output_snapshot(json_artifact_writer, "long_chapter_story_roles", result)

    assert [page.page_role for page in result.page_plan.planned_pages] == [
        "chapter_opening",
        "hero",
        "transition",
        "collage",
        "detail",
        "summary",
        "ending",
    ]
    assert result.page_plan.planned_pages[2].layout_family == "single_full_bleed"
    assert result.page_plan.planned_pages[4].layout_family == "single_full_bleed"
    assert result.page_plan.planned_pages[5].layout_family == "double_side_by_side"


def test_pagination_planning_node_simulated_storybook_prioritizes_strong_chapter_and_tracks_rerank(
    workflow_state_factory,
    json_artifact_writer,
):
    """验证强章节预算倾斜、主角曝光目标和候选方案 rerank 调试信息。"""
    cleaned_photo_set = {
        "album_id": "album-simulated",
        "valid_photos": [
            {
                "photo_id": "s1",
                "decision": "keep",
                "rank_weight": 0.98,
                "scene_tags": ["arrival"],
                "person_ids": ["hero-001"],
                "orientation": "landscape",
            },
            {
                "photo_id": "s2",
                "decision": "keep",
                "rank_weight": 0.95,
                "scene_tags": ["arrival"],
                "person_ids": ["hero-001"],
            },
            {
                "photo_id": "s3",
                "decision": "keep",
                "rank_weight": 0.92,
                "scene_tags": ["street"],
                "person_ids": ["hero-001"],
            },
            {
                "photo_id": "s4",
                "decision": "keep",
                "rank_weight": 0.9,
                "scene_tags": ["street"],
                "person_ids": ["hero-001"],
            },
            {
                "photo_id": "s5",
                "decision": "keep",
                "rank_weight": 0.88,
                "scene_tags": ["meal"],
                "person_ids": [],
            },
            {
                "photo_id": "s6",
                "decision": "keep",
                "rank_weight": 0.86,
                "scene_tags": ["meal"],
                "person_ids": [],
            },
            {
                "photo_id": "w1",
                "decision": "keep",
                "rank_weight": 0.35,
                "scene_tags": ["room"],
                "is_duplicate": True,
            },
            {
                "photo_id": "w2",
                "decision": "keep",
                "rank_weight": 0.32,
                "scene_tags": ["room"],
                "is_duplicate": True,
            },
            {
                "photo_id": "w3",
                "decision": "keep",
                "rank_weight": 0.3,
                "scene_tags": ["room"],
                "is_duplicate": True,
            },
            {
                "photo_id": "w4",
                "decision": "keep",
                "rank_weight": 0.28,
                "scene_tags": ["room"],
                "is_duplicate": True,
            },
            {
                "photo_id": "w5",
                "decision": "keep",
                "rank_weight": 0.26,
                "scene_tags": ["room"],
                "is_duplicate": True,
            },
            {
                "photo_id": "w6",
                "decision": "keep",
                "rank_weight": 0.24,
                "scene_tags": ["room"],
                "is_duplicate": True,
            },
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-simulated",
        "chapters": [
            {
                "chapter_id": "chapter-strong",
                "order": 1,
                "title_candidate": "高光章节",
                "cover_photo_id": "s1",
                "photo_ids": ["s1", "s2", "s3", "s4", "s5", "s6"],
            },
            {
                "chapter_id": "chapter-weak",
                "order": 2,
                "title_candidate": "补充章节",
                "photo_ids": ["w1", "w2", "w3", "w4", "w5", "w6"],
            },
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(min_pages=10, max_pages=10, hero_person_id="hero-001")

    result = pagination_planning_node(state)
    _save_planning_output_snapshot(json_artifact_writer, "simulated_storybook_rerank", result)

    budgets = {budget.chapter_id: budget.page_count for budget in result.page_plan.chapter_page_budgets}
    strong_roles = [page.page_role for page in result.page_plan.planned_pages if page.chapter_id == "chapter-strong"]
    hero_pages = [
        page
        for page in result.page_plan.planned_pages
        if any(photo_id.startswith("s") and "hero-001" in next(
            photo.person_ids
            for photo in result.cleaned_photo_set.valid_photos
            if photo.photo_id == photo_id
        ) for photo_id in page.candidate_photo_ids)
    ]

    assert budgets["chapter-strong"] > budgets["chapter-weak"]
    assert "transition" in strong_roles
    assert "summary" in strong_roles
    assert result.metadata["planning_debug"]["candidate_plan_count"] >= 2
    assert result.metadata["planning_debug"]["hero_focus_pages"] >= result.metadata["planning_debug"]["hero_focus_target"] >= 1
    assert len(hero_pages) >= result.metadata["planning_debug"]["hero_focus_target"]


def test_pagination_planning_node_applies_story_planner_suggestions(
    workflow_state_factory,
    json_artifact_writer,
    monkeypatch,
):
    """验证合法的故事策划器建议会覆盖对应页面角色与候选照片。"""
    class FakeStoryPlanner:
        def plan_chapter(self, planner_input):
            return story_planner_service.ChapterStorySuggestion(
                chapter_id=planner_input.chapter_id,
                provider="llm-test",
                chapter_theme="到达城市到晚餐收束",
                story_arc="arrival -> explore -> dinner",
                page_suggestions=[
                    story_planner_service.StoryPageSuggestion(
                        page_index=0,
                        page_role="chapter_opening",
                        candidate_photo_ids=["p2"],
                        narrative_purpose="以城市门头开场",
                    ),
                    story_planner_service.StoryPageSuggestion(
                        page_index=1,
                        page_role="hero",
                        candidate_photo_ids=["p4"],
                        narrative_purpose="主角高光页",
                    ),
                    story_planner_service.StoryPageSuggestion(
                        page_index=2,
                        page_role="summary",
                        candidate_photo_ids=["p1", "p3"],
                        narrative_purpose="用两张图总结过程",
                    ),
                    story_planner_service.StoryPageSuggestion(
                        page_index=3,
                        page_role="ending",
                        candidate_photo_ids=["p5"],
                        narrative_purpose="安静收束",
                    ),
                ],
            )

    monkeypatch.setattr(story_planner_service, "get_story_planner", lambda: FakeStoryPlanner())

    cleaned_photo_set = {
        "album_id": "album-llm",
        "valid_photos": [
            {"photo_id": "p1", "decision": "keep", "rank_weight": 0.91, "scene_tags": ["arrival"]},
            {"photo_id": "p2", "decision": "keep", "rank_weight": 0.87, "scene_tags": ["arrival"]},
            {"photo_id": "p3", "decision": "keep", "rank_weight": 0.7, "scene_tags": ["street"]},
            {"photo_id": "p4", "decision": "keep", "rank_weight": 0.95, "scene_tags": ["street"]},
            {"photo_id": "p5", "decision": "keep", "rank_weight": 0.62, "scene_tags": ["dinner"]},
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-llm",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "城市一日",
                "photo_ids": ["p1", "p2", "p3", "p4", "p5"],
            }
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(min_pages=4, max_pages=4)

    result = pagination_planning_node(state)
    _save_planning_output_snapshot(json_artifact_writer, "llm_story_planner_applied", result)

    assert [page.page_role for page in result.page_plan.planned_pages] == [
        "chapter_opening",
        "hero",
        "summary",
        "ending",
    ]
    assert result.page_plan.planned_pages[0].candidate_photo_ids == ["p2"]
    assert result.page_plan.planned_pages[1].candidate_photo_ids == ["p4"]
    assert result.page_plan.planned_pages[2].candidate_photo_ids == ["p1", "p3"]
    assert result.metadata["story_planner"]["provider"] == "llm-test"
    assert result.metadata["story_planner"]["chapters"][0]["chapter_theme"] == "到达城市到晚餐收束"


def test_pagination_planning_node_ignores_invalid_story_planner_photo_ids(
    workflow_state_factory,
    monkeypatch,
):
    """验证故事策划器返回非法照片时，节点会回退到规则结果并保持可用输出。"""
    class InvalidStoryPlanner:
        def plan_chapter(self, planner_input):
            return story_planner_service.ChapterStorySuggestion(
                chapter_id=planner_input.chapter_id,
                provider="llm-test",
                chapter_theme="无效建议测试",
                story_arc="invalid",
                page_suggestions=[
                    story_planner_service.StoryPageSuggestion(
                        page_index=0,
                        page_role="chapter_opening",
                        candidate_photo_ids=["not-exists"],
                    )
                ],
            )

    monkeypatch.setattr(story_planner_service, "get_story_planner", lambda: InvalidStoryPlanner())

    cleaned_photo_set = {
        "album_id": "album-invalid",
        "valid_photos": [
            {"photo_id": "p1", "decision": "keep", "rank_weight": 0.9},
            {"photo_id": "p2", "decision": "keep", "rank_weight": 0.8},
        ],
        "dropped_photos": [],
    }
    chapter_plan = {
        "album_id": "album-invalid",
        "chapters": [
            {
                "chapter_id": "chapter-001",
                "order": 1,
                "title_candidate": "无效章节",
                "photo_ids": ["p1", "p2"],
            }
        ],
    }

    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set, chapter_plan=chapter_plan)
    state.request.constraints = GenerateConstraints(min_pages=2, max_pages=2)

    result = pagination_planning_node(state)

    assert result.page_plan.planned_pages[0].candidate_photo_ids == ["p1"]
    assert result.metadata["story_planner"]["chapters"][0]["applied_page_indexes"] == [0]
