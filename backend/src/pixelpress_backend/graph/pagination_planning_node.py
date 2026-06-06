from __future__ import annotations
from pixelpress_backend.algorithms.pagination_planning import (
    build_candidate_page_allocations as _build_candidate_page_allocations,
    build_page_roles as _build_page_roles,
    build_photo_lookup as _build_photo_lookup,
    candidate_count_for_role as _candidate_count_for_role,
    compute_chapter_metrics as _compute_chapter_metrics,
    compute_hero_focus_target as _compute_hero_focus_target,
    estimate_total_pages as _estimate_total_pages,
    filter_chapter_photo_ids as _filter_chapter_photo_ids,
    filter_chapter_sequence_photo_ids as _filter_chapter_sequence_photo_ids,
    is_spread_candidate as _is_spread_candidate,
    page_contains_hero as _page_contains_hero,
    pick_candidate_photo_ids as _pick_candidate_photo_ids,
    resolve_layout_family as _resolve_layout_family,
    resolve_text_need as _resolve_text_need,
    score_page_plan as _score_page_plan,
)
from pixelpress_backend.models.domain import GenerateConstraints
from pixelpress_backend.models.workflow_contracts import (
    ChapterPlanItem,
    KeptPhoto,
    PaginationPlanningInput,
    PaginationPlanningOutput,
    PagePlan,
    PlannedPage,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState
from pixelpress_backend.services import story_planner as story_planner_service


"""页面规划节点。

职责:
- 消费 `state.chapter_plan` 和清洗后的候选照片。
- 产出 `state.page_plan`，定义章节页数预算和页面角色。

输入:
- `state.chapter_plan`
- `state.cleaned_photo_set`
- `state.request.constraints`

输出:
- `state.page_plan`

禁止:
- 不要直接生成几何坐标
- 不要写 `state.page_layouts`
- 不要修改最终布局版本

TODO:
- 决定总页数、章节页数、跨页候选、多图拼版候选和主视觉候选
- 支持主角人物曝光率、avoid_spread 等约束
"""


SUPPORTED_PAGE_ROLES = {
    "chapter_opening",
    "hero",
    "transition",
    "collage",
    "detail",
    "summary",
    "ending",
}


def _build_story_planner_input(
    album_id: str,
    chapter: ChapterPlanItem,
    page_roles: list[str],
    chapter_sequence_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
) -> story_planner_service.ChapterStoryPlannerInput:
    """组装章节故事策划器输入。

    这里会把规则层已有的页角色骨架、章节照片摘要和用户约束转换为模型可消费的结构化对象。
    """
    photo_summaries = [
        story_planner_service.StoryPhotoSummary(
            photo_id=photo_id,
            rank_weight=photo_lookup[photo_id].rank_weight,
            person_ids=photo_lookup[photo_id].person_ids,
            scene_tags=photo_lookup[photo_id].scene_tags,
            orientation=photo_lookup[photo_id].orientation,
            is_duplicate=photo_lookup[photo_id].is_duplicate,
            captured_at=photo_lookup[photo_id].captured_at.isoformat() if photo_lookup[photo_id].captured_at else None,
        )
        for photo_id in chapter_sequence_photo_ids
        if photo_id in photo_lookup
    ]
    return story_planner_service.ChapterStoryPlannerInput(
        album_id=album_id,
        chapter_id=chapter.chapter_id,
        title_candidate=chapter.title_candidate,
        cover_photo_id=chapter.cover_photo_id,
        page_roles=page_roles,
        constraints=constraints,
        photo_summaries=photo_summaries,
    )


def _normalize_story_suggestion_maps(
    story_suggestion: story_planner_service.ChapterStorySuggestion | None,
    page_count: int,
    valid_photo_ids: set[str],
) -> dict[int, dict[str, object]]:
    """清洗并标准化模型返回的页面建议。

    仅保留页数范围内、角色合法且照片属于本章候选池的建议。
    """
    if story_suggestion is None:
        return {}
    story_page_map: dict[int, dict[str, object]] = {}
    for page_suggestion in story_suggestion.page_suggestions:
        if page_suggestion.page_index < 0 or page_suggestion.page_index >= page_count:
            continue
        # 模型只能在既定页数和本章合法照片池内给建议，越界或脏数据在这里被拦掉。
        effective_role = page_suggestion.page_role if page_suggestion.page_role in SUPPORTED_PAGE_ROLES else None
        candidate_photo_ids: list[str] = []
        for photo_id in page_suggestion.candidate_photo_ids:
            if photo_id in valid_photo_ids and photo_id not in candidate_photo_ids:
                candidate_photo_ids.append(photo_id)
        story_page_map[page_suggestion.page_index] = {
            "page_role": effective_role,
            "candidate_photo_ids": candidate_photo_ids,
            "narrative_purpose": page_suggestion.narrative_purpose,
            "reason": page_suggestion.reason,
        }
    return story_page_map


def _merge_story_suggested_photo_ids(
    base_page_role: str,
    story_page_suggestion: dict[str, object] | None,
    heuristic_photo_ids: list[str],
) -> tuple[str, list[str]]:
    """合并模型建议与规则选图结果。

    模型优先表达叙事意图，规则负责补齐缺失候选，确保最终输出满足页面数量要求。
    """
    # 模型负责“更像故事”的软建议，规则层负责补齐数量和兜底，最终结果仍保持可控。
    effective_page_role = base_page_role
    if story_page_suggestion and isinstance(story_page_suggestion.get("page_role"), str):
        effective_page_role = str(story_page_suggestion["page_role"])
    desired_count = _candidate_count_for_role(effective_page_role)
    merged_ids: list[str] = []
    if story_page_suggestion:
        for photo_id in story_page_suggestion.get("candidate_photo_ids", []):
            if len(merged_ids) == desired_count:
                break
            if photo_id not in merged_ids:
                merged_ids.append(photo_id)
    for photo_id in heuristic_photo_ids:
        if len(merged_ids) == desired_count:
            break
        if photo_id not in merged_ids:
            merged_ids.append(photo_id)
    return effective_page_role, merged_ids


def _build_planned_pages_for_candidate(
    album_id: str,
    chapters: list[ChapterPlanItem],
    chapter_page_counts: dict[str, int],
    chapter_metrics: dict[str, dict[str, float | int | bool]],
    chapter_ranked_photo_map: dict[str, list[str]],
    chapter_sequence_photo_map: dict[str, list[str]],
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
    story_planner: story_planner_service.ChapterStoryPlanner | None = None,
) -> tuple[list[PlannedPage], list[dict[str, int | str]], int, int, list[dict[str, object]]]:
    """基于单个章节页数预算方案生成完整页面规划。

    当传入 story_planner 时，本函数会在规则骨架上叠加模型的章节故事建议。
    """
    planned_pages: list[PlannedPage] = []
    chapter_page_budgets: list[dict[str, int | str]] = []
    page_number = 1
    used_photo_ids: set[str] = set()
    hero_focus_pages = 0
    hero_focus_target = _compute_hero_focus_target(chapter_metrics, sum(chapter_page_counts.values()), constraints)
    chapter_story_plans: list[dict[str, object]] = []

    for chapter in chapters:
        chapter_ranked_photo_ids = chapter_ranked_photo_map[chapter.chapter_id]
        chapter_sequence_photo_ids = chapter_sequence_photo_map[chapter.chapter_id]
        page_roles = _build_page_roles(chapter_page_counts[chapter.chapter_id])
        story_suggestion = None
        story_page_map: dict[int, dict[str, object]] = {}
        if story_planner is not None:
            # 大模型先理解“这一章想讲什么”，再给每一页一个角色和选图建议。
            story_suggestion = story_planner.plan_chapter(
                _build_story_planner_input(
                    album_id,
                    chapter,
                    page_roles,
                    chapter_sequence_photo_ids,
                    photo_lookup,
                    constraints,
                )
            )
            story_page_map = _normalize_story_suggestion_maps(
                story_suggestion,
                len(page_roles),
                set(chapter_ranked_photo_ids),
            )
        start_page = page_number
        chapter_metrics_snapshot = chapter_metrics[chapter.chapter_id]
        for page_index, page_role in enumerate(page_roles):
            previous_page_photo_ids = set(planned_pages[-1].candidate_photo_ids) if planned_pages else set()
            story_page_suggestion = story_page_map.get(page_index)
            prefer_hero = (
                constraints.hero_person_id is not None
                and hero_focus_pages < hero_focus_target
                and int(chapter_metrics_snapshot["hero_photo_count"]) > 0
                and page_role in {"hero", "detail", "summary", "transition"}
            )
            heuristic_photo_ids = _pick_candidate_photo_ids(
                page_role,
                chapter,
                chapter_ranked_photo_ids,
                chapter_sequence_photo_ids,
                photo_lookup,
                constraints,
                used_photo_ids,
                previous_page_photo_ids,
                prefer_hero,
            )
            effective_page_role, candidate_photo_ids = _merge_story_suggested_photo_ids(
                page_role,
                story_page_suggestion,
                heuristic_photo_ids,
            )
            # 页面角色可能被模型重写，但版式族、跨页与文本需求仍统一由规则层收口。
            primary_photo = photo_lookup.get(candidate_photo_ids[0]) if candidate_photo_ids else None
            is_spread = effective_page_role == "hero" and _is_spread_candidate(primary_photo, constraints)
            previous_layout_family = planned_pages[-1].layout_family if planned_pages else None
            prior_collage_count = sum(1 for page in planned_pages if page.page_role == "collage")
            layout_family = _resolve_layout_family(
                effective_page_role,
                len(candidate_photo_ids),
                previous_layout_family,
                is_spread,
                prior_collage_count,
            )
            planned_pages.append(
                PlannedPage(
                    page_id=f"page-{page_number:03d}",
                    chapter_id=chapter.chapter_id,
                    page_role=effective_page_role,
                    candidate_photo_ids=candidate_photo_ids,
                    layout_family=layout_family,
                    is_spread=is_spread,
                    text_need=_resolve_text_need(effective_page_role),
                )
            )
            used_photo_ids.update(candidate_photo_ids)
            if _page_contains_hero(candidate_photo_ids, photo_lookup, constraints.hero_person_id):
                hero_focus_pages += 1
            page_number += 1
        if story_suggestion is not None:
            chapter_story_plans.append(
                {
                    **story_suggestion.model_dump(mode="python"),
                    "page_count": len(page_roles),
                    "applied_page_indexes": sorted(story_page_map.keys()),
                }
            )
        chapter_page_budgets.append(
            {
                "chapter_id": chapter.chapter_id,
                "start_page": start_page,
                "end_page": page_number - 1,
                "page_count": len(page_roles),
            }
        )
    return planned_pages, chapter_page_budgets, hero_focus_pages, hero_focus_target, chapter_story_plans


def _score_page_plan(
    chapters: list[ChapterPlanItem],
    planned_pages: list[PlannedPage],
    chapter_page_budgets: list[dict[str, int | str]],
    chapter_metrics: dict[str, dict[str, float | int | bool]],
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
    hero_focus_pages: int,
    hero_focus_target: int,
) -> float:
    """为单个分页方案计算规则代理分。

    该分数用于在多个候选方案中选出更稳定、更像故事书结构的结果。
    """
    if not planned_pages:
        return float("-inf")

    # 评分不是审美分，而是“这套分页是否更像一本可读的故事相册”的规则代理分。
    score = 0.0
    unique_selected_photo_ids = {photo_id for page in planned_pages for photo_id in page.candidate_photo_ids}
    score += len(unique_selected_photo_ids) * 0.25

    adjacent_repeat_penalty = 0
    same_layout_penalty = 0
    for previous_page, current_page in zip(planned_pages, planned_pages[1:]):
        adjacent_repeat_penalty += len(set(previous_page.candidate_photo_ids) & set(current_page.candidate_photo_ids))
        if previous_page.layout_family == current_page.layout_family:
            same_layout_penalty += 1
    score -= adjacent_repeat_penalty * 4.0
    score -= same_layout_penalty * 0.6

    if hero_focus_target > 0:
        score += min(hero_focus_pages, hero_focus_target) * 1.5
        score -= max(hero_focus_target - hero_focus_pages, 0) * 2.0

    chapter_pages = {
        budget["chapter_id"]: [
            page for page in planned_pages if page.chapter_id == budget["chapter_id"]
        ]
        for budget in chapter_page_budgets
    }
    for chapter in chapters:
        chapter_id = chapter.chapter_id
        pages = chapter_pages.get(chapter_id, [])
        page_count = len(pages)
        roles = [page.page_role for page in pages]
        score += float(chapter_metrics[chapter_id]["strength_score"]) * page_count * 0.03
        if roles and roles[0] == "chapter_opening":
            score += 0.5
        if page_count >= 2 and "hero" in roles:
            score += 0.8
        if page_count >= 4 and "collage" in roles:
            score += 0.7
        if page_count >= 5 and "transition" in roles:
            score += 0.8
        if page_count >= 5 and "summary" in roles:
            score += 0.8
        if page_count >= 6 and "detail" in roles:
            score += 0.6
        if roles and roles[-1] == "ending":
            score += 0.5

    if constraints.hero_person_id is not None:
        hero_focus_photo_score = 0.0
        for page in planned_pages:
            if _page_contains_hero(page.candidate_photo_ids, photo_lookup, constraints.hero_person_id):
                hero_focus_photo_score += 0.25
        score += hero_focus_photo_score

    return score


def pagination_planning_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    """执行页面规划节点。

    流程分为两轮：第一轮纯规则生成并筛选分页骨架，第二轮在最佳骨架上叠加模型建议，
    最终输出结构化的 `PagePlan` 与调试信息。
    """
    node_input = PaginationPlanningInput(
        album_id=state.request.album_id,
        book_size=state.request.book_size,
        binding=state.request.binding,
        style=state.request.style,
        constraints=state.request.constraints,
        chapters=state.chapter_plan.chapters if state.chapter_plan else [],
        photo_pool=state.cleaned_photo_set.valid_photos if state.cleaned_photo_set else [],
    )

    photo_lookup = _build_photo_lookup(node_input.photo_pool, node_input.constraints)
    chapters = node_input.chapters or [
        ChapterPlanItem(
            chapter_id="chapter-001",
            order=1,
            title_candidate="默认章节",
            photo_ids=[],
        )
    ]
    chapter_ranked_photo_map = {
        chapter.chapter_id: _filter_chapter_photo_ids(chapter, photo_lookup, node_input.constraints) for chapter in chapters
    }
    chapter_sequence_photo_map = {
        chapter.chapter_id: _filter_chapter_sequence_photo_ids(chapter, photo_lookup, node_input.constraints) for chapter in chapters
    }
    chapter_metrics = _compute_chapter_metrics(
        chapters,
        chapter_ranked_photo_map,
        chapter_sequence_photo_map,
        photo_lookup,
        node_input.constraints,
    )
    total_pages = _estimate_total_pages(chapters, chapter_metrics, node_input.constraints)
    candidate_page_allocations = _build_candidate_page_allocations(
        chapters,
        chapter_metrics,
        total_pages,
        node_input.constraints,
    )
    candidate_results = []
    for candidate_index, chapter_page_counts in enumerate(candidate_page_allocations):
        # 第一轮完全走规则，目的是先找到结构上最稳的分页骨架。
        planned_pages, chapter_page_budgets, hero_focus_pages, hero_focus_target, _ = _build_planned_pages_for_candidate(
            node_input.album_id,
            chapters,
            chapter_page_counts,
            chapter_metrics,
            chapter_ranked_photo_map,
            chapter_sequence_photo_map,
            photo_lookup,
            node_input.constraints,
        )
        candidate_score = _score_page_plan(
            chapters,
            planned_pages,
            chapter_page_budgets,
            chapter_metrics,
            photo_lookup,
            node_input.constraints,
            hero_focus_pages,
            hero_focus_target,
        )
        candidate_results.append(
            {
                "index": candidate_index,
                "score": candidate_score,
                "page_counts": chapter_page_counts,
                "planned_pages": planned_pages,
                "chapter_page_budgets": chapter_page_budgets,
                "hero_focus_pages": hero_focus_pages,
                "hero_focus_target": hero_focus_target,
            }
        )

    best_candidate = max(candidate_results, key=lambda candidate: candidate["score"])
    story_planner = story_planner_service.get_story_planner()
    # 第二轮只在最佳骨架上叠加模型建议，避免模型把页数预算和章节节奏完全带偏。
    planned_pages, chapter_page_budgets, hero_focus_pages, hero_focus_target, chapter_story_plans = _build_planned_pages_for_candidate(
        node_input.album_id,
        chapters,
        best_candidate["page_counts"],
        chapter_metrics,
        chapter_ranked_photo_map,
        chapter_sequence_photo_map,
        photo_lookup,
        node_input.constraints,
        story_planner=story_planner,
    )
    best_candidate["hero_focus_pages"] = hero_focus_pages
    best_candidate["hero_focus_target"] = hero_focus_target

    selected_photo_ids = {photo_id for page in planned_pages for photo_id in page.candidate_photo_ids}
    eligible_photo_ids = {
        photo_id for chapter_photo_ids in chapter_ranked_photo_map.values() for photo_id in chapter_photo_ids
    }
    page_plan = PagePlan(
        total_pages=len(planned_pages),
        chapter_page_budgets=chapter_page_budgets,
        planned_pages=planned_pages,
    )
    planning_output = PaginationPlanningOutput(
        album_id=node_input.album_id,
        page_plan=page_plan,
        planning_summary={
            "selected_photo_count": len(selected_photo_ids),
            "unused_photo_count": max(len(eligible_photo_ids - selected_photo_ids), 0),
            "spread_count": sum(1 for page in planned_pages if page.is_spread),
        },
    )
    state.page_plan = planning_output.page_plan
    state.metadata["planning_summary"] = planning_output.planning_summary.model_dump(mode="python")
    state.metadata["planning_debug"] = {
        "candidate_plan_count": len(candidate_page_allocations),
        "selected_candidate_index": best_candidate["index"],
        "selected_candidate_score": best_candidate["score"],
        "hero_focus_pages": best_candidate["hero_focus_pages"],
        "hero_focus_target": best_candidate["hero_focus_target"],
        "chapter_strengths": {
            chapter_id: round(float(metrics["strength_score"]), 3) for chapter_id, metrics in chapter_metrics.items()
        },
    }
    if chapter_story_plans:
        state.metadata["story_planner"] = {
            "provider": chapter_story_plans[0]["provider"],
            "chapters": chapter_story_plans,
        }
    return state
