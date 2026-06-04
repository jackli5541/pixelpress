from __future__ import annotations

from math import ceil

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


def _photo_sort_key(photo: KeptPhoto, *, must_include: set[str], hero_person_id: str | None) -> tuple[int, int, int, int, float]:
    include_priority = 0 if photo.photo_id in must_include else 1
    hero_priority = 0 if hero_person_id and hero_person_id in photo.person_ids else 1
    keep_priority = 0 if photo.decision == "keep" else 1
    duplicate_priority = 1 if photo.is_duplicate else 0
    return (include_priority, hero_priority, keep_priority, duplicate_priority, -photo.rank_weight)


def _build_photo_lookup(photo_pool: list[KeptPhoto], constraints: GenerateConstraints) -> dict[str, KeptPhoto]:
    ordered_photos = sorted(
        photo_pool,
        key=lambda item: _photo_sort_key(
            item,
            must_include=set(constraints.must_include),
            hero_person_id=constraints.hero_person_id,
        ),
    )
    return {photo.photo_id: photo for photo in ordered_photos}


def _filter_chapter_photo_ids(
    chapter: ChapterPlanItem,
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
) -> list[str]:
    excluded = set(constraints.must_exclude)
    chapter_photo_ids = [
        photo_id for photo_id in chapter.photo_ids if photo_id in photo_lookup and photo_id not in excluded
    ]
    chapter_photo_ids.sort(
        key=lambda photo_id: _photo_sort_key(
            photo_lookup[photo_id],
            must_include=set(constraints.must_include),
            hero_person_id=constraints.hero_person_id,
        )
    )
    if chapter.cover_photo_id and chapter.cover_photo_id in chapter_photo_ids:
        chapter_photo_ids.remove(chapter.cover_photo_id)
        chapter_photo_ids.insert(0, chapter.cover_photo_id)
    return chapter_photo_ids


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _estimate_total_pages(
    chapters: list[ChapterPlanItem],
    chapter_photo_map: dict[str, list[str]],
    constraints: GenerateConstraints,
) -> int:
    chapter_count = max(len(chapters), 1)
    total_photo_count = sum(len(photo_ids) for photo_ids in chapter_photo_map.values())
    estimated_pages = chapter_count + ceil(max(total_photo_count - chapter_count, 0) / 2)
    return _clamp(estimated_pages, max(constraints.min_pages, 1), max(constraints.max_pages, 1))


def _allocate_chapter_page_counts(
    chapters: list[ChapterPlanItem],
    chapter_photo_map: dict[str, list[str]],
    total_pages: int,
) -> dict[str, int]:
    if not chapters:
        return {"chapter-001": total_pages}

    chapter_page_counts = {chapter.chapter_id: 1 for chapter in chapters}
    remaining_pages = max(total_pages - len(chapters), 0)
    if remaining_pages == 0:
        return chapter_page_counts

    weighted_counts = {chapter.chapter_id: max(len(chapter_photo_map[chapter.chapter_id]), 1) for chapter in chapters}
    total_weight = sum(weighted_counts.values())
    remainders: list[tuple[float, int, str]] = []
    distributed = 0

    for order, chapter in enumerate(chapters):
        exact_share = remaining_pages * weighted_counts[chapter.chapter_id] / total_weight
        extra_pages = int(exact_share)
        chapter_page_counts[chapter.chapter_id] += extra_pages
        distributed += extra_pages
        remainders.append((exact_share - extra_pages, -order, chapter.chapter_id))

    for _, _, chapter_id in sorted(remainders, reverse=True)[: remaining_pages - distributed]:
        chapter_page_counts[chapter_id] += 1

    return chapter_page_counts


def _build_page_roles(page_count: int) -> list[str]:
    if page_count <= 1:
        return ["chapter_opening"]
    if page_count == 2:
        return ["chapter_opening", "hero"]
    if page_count == 3:
        return ["chapter_opening", "hero", "ending"]
    return ["chapter_opening", "hero", *(["collage"] * (page_count - 3)), "ending"]


def _candidate_count_for_role(role: str) -> int:
    if role == "collage":
        return 2
    return 1


def _is_spread_candidate(photo: KeptPhoto | None, constraints: GenerateConstraints) -> bool:
    if constraints.avoid_spread or photo is None:
        return False
    return photo.orientation == "landscape" and not photo.is_duplicate and photo.rank_weight >= 0.85


def _pick_candidate_photo_ids(
    role: str,
    chapter: ChapterPlanItem,
    chapter_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    cursor: int,
) -> tuple[list[str], int]:
    if not chapter_photo_ids:
        return [], cursor

    if role == "chapter_opening" and chapter.cover_photo_id and chapter.cover_photo_id in chapter_photo_ids:
        return [chapter.cover_photo_id], max(cursor, chapter_photo_ids.index(chapter.cover_photo_id) + 1)

    desired_count = _candidate_count_for_role(role)
    picked_photo_ids = chapter_photo_ids[cursor : cursor + desired_count]
    if picked_photo_ids:
        return picked_photo_ids, min(cursor + len(picked_photo_ids), len(chapter_photo_ids))

    # If the chapter runs out of unique photos, reuse the strongest remaining photo
    # so the planner still produces a non-empty candidate list for the page.
    return [chapter_photo_ids[-1]], len(chapter_photo_ids)


def _resolve_layout_family(role: str) -> str:
    if role == "chapter_opening":
        return "chapter_cover"
    if role == "hero":
        return "single_full_bleed"
    if role == "collage":
        return "grid_nine"
    return "double_side_by_side"


def _resolve_text_need(role: str) -> str:
    return "chapter_title" if role == "chapter_opening" else "none"


def pagination_planning_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
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
    chapter_photo_map = {
        chapter.chapter_id: _filter_chapter_photo_ids(chapter, photo_lookup, node_input.constraints) for chapter in chapters
    }
    total_pages = _estimate_total_pages(chapters, chapter_photo_map, node_input.constraints)
    chapter_page_counts = _allocate_chapter_page_counts(chapters, chapter_photo_map, total_pages)

    planned_pages: list[PlannedPage] = []
    chapter_page_budgets = []
    page_number = 1
    for chapter in chapters:
        chapter_photo_ids = chapter_photo_map[chapter.chapter_id]
        page_roles = _build_page_roles(chapter_page_counts[chapter.chapter_id])
        start_page = page_number
        cursor = 0
        for page_role in page_roles:
            candidate_photo_ids, cursor = _pick_candidate_photo_ids(
                page_role,
                chapter,
                chapter_photo_ids,
                photo_lookup,
                cursor,
            )
            primary_photo = photo_lookup.get(candidate_photo_ids[0]) if candidate_photo_ids else None
            is_spread = page_role == "hero" and _is_spread_candidate(primary_photo, node_input.constraints)
            layout_family = "spread_full_bleed" if is_spread else _resolve_layout_family(page_role)
            planned_pages.append(
                PlannedPage(
                    page_id=f"page-{page_number:03d}",
                    chapter_id=chapter.chapter_id,
                    page_role=page_role,
                    candidate_photo_ids=candidate_photo_ids,
                    layout_family=layout_family,
                    is_spread=is_spread,
                    text_need=_resolve_text_need(page_role),
                )
            )
            page_number += 1
        chapter_page_budgets.append(
            {
                "chapter_id": chapter.chapter_id,
                "start_page": start_page,
                "end_page": page_number - 1,
                "page_count": len(page_roles),
            }
        )

    selected_photo_ids = {photo_id for page in planned_pages for photo_id in page.candidate_photo_ids}
    eligible_photo_ids = {
        photo_id for chapter_photo_ids in chapter_photo_map.values() for photo_id in chapter_photo_ids
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
    return state
