"""分页规划算法模块。

纯函数实现，不依赖 LangGraph State，可独立测试。
"""

from __future__ import annotations

from math import ceil

from pixelpress_backend.models.domain import GenerateConstraints
from pixelpress_backend.models.workflow_contracts import (
    ChapterPlanItem,
    KeptPhoto,
    PlannedPage,
)


def photo_sort_key(
    photo: KeptPhoto,
    *,
    must_include: set[str],
    hero_person_id: str | None,
) -> tuple[int, int, int, int, float]:
    """生成照片排序键。

    排序目标是为章节分页提供统一的候选优先级，优先满足硬约束和重点人物曝光，
    再兼顾清洗决策、去重状态与质量分。
    """
    include_priority = 0 if photo.photo_id in must_include else 1
    hero_priority = 0 if hero_person_id and hero_person_id in photo.person_ids else 1
    keep_priority = 0 if photo.decision == "keep" else 1
    duplicate_priority = 1 if photo.is_duplicate else 0
    return (include_priority, hero_priority, keep_priority, duplicate_priority, -photo.rank_weight)


def build_photo_lookup(
    photo_pool: list[KeptPhoto],
    constraints: GenerateConstraints,
) -> dict[str, KeptPhoto]:
    """构建按规划优先级排序后的照片索引。"""
    ordered_photos = sorted(
        photo_pool,
        key=lambda item: photo_sort_key(
            item,
            must_include=set(constraints.must_include),
            hero_person_id=constraints.hero_person_id,
        ),
    )
    return {photo.photo_id: photo for photo in ordered_photos}


def filter_chapter_photo_ids(
    chapter: ChapterPlanItem,
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
) -> list[str]:
    """返回适用于章节分页的“排序池”照片列表。

    该列表用于重点页和兜底逻辑，特点是已经过约束过滤，并按规划优先级排序。
    """
    excluded = set(constraints.must_exclude)
    chapter_photo_ids = [
        photo_id for photo_id in chapter.photo_ids if photo_id in photo_lookup and photo_id not in excluded
    ]
    chapter_photo_ids.sort(
        key=lambda photo_id: photo_sort_key(
            photo_lookup[photo_id],
            must_include=set(constraints.must_include),
            hero_person_id=constraints.hero_person_id,
        )
    )
    if chapter.cover_photo_id and chapter.cover_photo_id in chapter_photo_ids:
        chapter_photo_ids.remove(chapter.cover_photo_id)
        chapter_photo_ids.insert(0, chapter.cover_photo_id)
    return chapter_photo_ids


def filter_chapter_sequence_photo_ids(
    chapter: ChapterPlanItem,
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
) -> list[str]:
    """返回保留原始叙事顺序的章节照片列表。

    该列表主要服务于 transition、collage、ending 等更依赖上下文顺序的页面角色。
    """
    excluded = set(constraints.must_exclude)
    return [photo_id for photo_id in chapter.photo_ids if photo_id in photo_lookup and photo_id not in excluded]


def clamp(value: int, minimum: int, maximum: int) -> int:
    """将整数限制在给定区间内。"""
    return max(minimum, min(value, maximum))


def compute_chapter_metrics(
    chapters: list[ChapterPlanItem],
    chapter_ranked_photo_map: dict[str, list[str]],
    chapter_sequence_photo_map: dict[str, list[str]],
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
) -> dict[str, dict[str, float | int | bool]]:
    """计算章节强度指标。

    返回值会被页数预算、主角曝光目标和候选方案评分共同使用，
    是节点三判断“哪一章更值得多讲几页”的核心基础数据。
    """
    chapter_metrics: dict[str, dict[str, float | int | bool]] = {}
    for chapter in chapters:
        chapter_id = chapter.chapter_id
        ranked_ids = chapter_ranked_photo_map.get(chapter_id, [])
        sequence_ids = chapter_sequence_photo_map.get(chapter_id, [])
        photos = [photo_lookup[photo_id] for photo_id in sequence_ids if photo_id in photo_lookup]
        photo_count = len(sequence_ids)
        avg_rank = (
            sum(photo_lookup[photo_id].rank_weight for photo_id in ranked_ids) / len(ranked_ids) if ranked_ids else 0.0
        )
        strong_photo_count = sum(1 for photo_id in ranked_ids if photo_lookup[photo_id].rank_weight >= 0.85)
        hero_photo_count = sum(
            1
            for photo in photos
            if constraints.hero_person_id is not None and constraints.hero_person_id in photo.person_ids
        )
        scene_tags = {tag for photo in photos for tag in photo.scene_tags} | set(chapter.scene_tags)
        scene_diversity = len(scene_tags)
        strength_score = (
            max(photo_count, 1)
            + (avg_rank * 2.0)
            + (min(scene_diversity, 4) * 0.75)
            + (strong_photo_count * 0.8)
            + (hero_photo_count * 0.9)
            + (0.4 if chapter.cover_photo_id else 0.0)
        )
        chapter_metrics[chapter_id] = {
            "photo_count": photo_count,
            "avg_rank": avg_rank,
            "strong_photo_count": strong_photo_count,
            "hero_photo_count": hero_photo_count,
            "scene_diversity": scene_diversity,
            "strength_score": strength_score,
            "has_cover": chapter.cover_photo_id is not None,
        }
    return chapter_metrics


def estimate_total_pages(
    chapters: list[ChapterPlanItem],
    chapter_metrics: dict[str, dict[str, float | int | bool]],
    constraints: GenerateConstraints,
) -> int:
    """估算整本书的总页数。

    估算同时考虑章节数量、可用照片数量和强图密度，最后受输入约束裁剪。
    """
    chapter_count = max(len(chapters), 1)
    total_photo_count = sum(int(metrics["photo_count"]) for metrics in chapter_metrics.values())
    strong_photo_bonus = sum(int(metrics["strong_photo_count"]) for metrics in chapter_metrics.values())
    estimated_pages = chapter_count + ceil(max(total_photo_count - chapter_count, 0) / 2) + min(strong_photo_bonus // 4, 2)
    return clamp(estimated_pages, max(constraints.min_pages, 1), max(constraints.max_pages, 1))


def compute_hero_focus_target(
    chapter_metrics: dict[str, dict[str, float | int | bool]],
    total_pages: int,
    constraints: GenerateConstraints,
) -> int:
    """计算全书主角重点曝光页目标值。"""
    if constraints.hero_person_id is None:
        return 0
    hero_chapters = sum(1 for metrics in chapter_metrics.values() if int(metrics["hero_photo_count"]) > 0)
    if hero_chapters == 0:
        return 0
    return min(max(hero_chapters, 1), max(total_pages // 3, 1))


def allocate_chapter_page_counts(
    chapters: list[ChapterPlanItem],
    chapter_metrics: dict[str, dict[str, float | int | bool]],
    total_pages: int,
    constraints: GenerateConstraints,
) -> dict[str, int]:
    """按章节强度分配页数预算。

    规则为：每章至少一页，优先保证主角章节获得重点页，再按章节强度进行加权分配。
    """
    if not chapters:
        return {"chapter-001": total_pages}

    chapter_page_counts = {chapter.chapter_id: 1 for chapter in chapters}
    remaining_pages = max(total_pages - len(chapters), 0)
    if remaining_pages == 0:
        return chapter_page_counts

    hero_focus_target = compute_hero_focus_target(chapter_metrics, total_pages, constraints)
    hero_chapters = sorted(
        [chapter for chapter in chapters if int(chapter_metrics[chapter.chapter_id]["hero_photo_count"]) > 0],
        key=lambda chapter: (
            int(chapter_metrics[chapter.chapter_id]["hero_photo_count"]),
            float(chapter_metrics[chapter.chapter_id]["strength_score"]),
        ),
        reverse=True,
    )
    for chapter in hero_chapters[:hero_focus_target]:
        if remaining_pages <= 0:
            break
        chapter_page_counts[chapter.chapter_id] += 1
        remaining_pages -= 1

    if remaining_pages == 0:
        return chapter_page_counts

    weighted_counts = {
        chapter.chapter_id: max(float(chapter_metrics[chapter.chapter_id]["strength_score"]), 1.0) for chapter in chapters
    }
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


def build_candidate_page_allocations(
    chapters: list[ChapterPlanItem],
    chapter_metrics: dict[str, dict[str, float | int | bool]],
    total_pages: int,
    constraints: GenerateConstraints,
) -> list[dict[str, int]]:
    """生成少量章节页数预算候选方案。

    这些方案会在后续通过规则评分做 rerank，用来替代一次性拍板的单一预算。
    """
    base_counts = allocate_chapter_page_counts(chapters, chapter_metrics, total_pages, constraints)
    variants: list[dict[str, int]] = [base_counts]
    if len(chapters) < 2:
        return variants

    def donor_candidates() -> list[ChapterPlanItem]:
        """找出可以向其他章节让渡页数的候选章节。"""
        return [
            chapter
            for chapter in chapters
            if base_counts[chapter.chapter_id] > 1
        ]

    donors = sorted(
        donor_candidates(),
        key=lambda chapter: (
            base_counts[chapter.chapter_id],
            -float(chapter_metrics[chapter.chapter_id]["strength_score"]),
        ),
    )
    if not donors:
        return variants

    strongest_chapter = max(chapters, key=lambda chapter: float(chapter_metrics[chapter.chapter_id]["strength_score"]))
    hero_rich_chapter = max(
        chapters,
        key=lambda chapter: (
            int(chapter_metrics[chapter.chapter_id]["hero_photo_count"]),
            float(chapter_metrics[chapter.chapter_id]["strength_score"]),
        ),
    )
    scene_rich_chapter = max(
        chapters,
        key=lambda chapter: (
            int(chapter_metrics[chapter.chapter_id]["scene_diversity"]),
            float(chapter_metrics[chapter.chapter_id]["avg_rank"]),
        ),
    )

    for target_chapter in [strongest_chapter, hero_rich_chapter, scene_rich_chapter]:
        donor = next((chapter for chapter in donors if chapter.chapter_id != target_chapter.chapter_id), None)
        if donor is None:
            continue
        variant = dict(base_counts)
        variant[donor.chapter_id] -= 1
        variant[target_chapter.chapter_id] += 1
        variants.append(variant)

    deduped_variants: list[dict[str, int]] = []
    seen_signatures: set[tuple[int, ...]] = set()
    for variant in variants:
        signature = tuple(variant[chapter.chapter_id] for chapter in chapters)
        if signature not in seen_signatures:
            seen_signatures.add(signature)
            deduped_variants.append(variant)
    return deduped_variants


def build_page_roles(page_count: int) -> list[str]:
    """根据章节页数生成页面角色序列。"""
    if page_count <= 1:
        return ["chapter_opening"]
    if page_count == 2:
        return ["chapter_opening", "hero"]
    if page_count == 3:
        return ["chapter_opening", "hero", "ending"]
    if page_count == 4:
        return ["chapter_opening", "hero", "collage", "ending"]
    middle_roles = ["transition"]
    middle_slots = page_count - 5
    for index in range(middle_slots):
        middle_roles.append("collage" if index % 2 == 0 else "detail")
    return ["chapter_opening", "hero", *middle_roles, "summary", "ending"]


def candidate_count_for_role(role: str) -> int:
    """返回页面角色对应的目标候选照片数。"""
    if role == "collage":
        return 2
    if role == "summary":
        return 2
    if role == "ending":
        return 2
    return 1


def is_spread_candidate(photo: KeptPhoto | None, constraints: GenerateConstraints) -> bool:
    """判断某张照片是否适合作为跨页候选。"""
    if constraints.avoid_spread or photo is None:
        return False
    return photo.orientation == "landscape" and not photo.is_duplicate and photo.rank_weight >= 0.85


def pick_fallback_photo_ids(
    chapter_ranked_photo_ids: list[str],
    previous_page_photo_ids: set[str],
    desired_count: int,
) -> list[str]:
    """在角色选图失败时提供兜底候选。

    兜底逻辑优先避免与上一页重复，其次保证页面永远有足够数量的候选照片。
    """
    fallback_ids = [photo_id for photo_id in chapter_ranked_photo_ids if photo_id not in previous_page_photo_ids]
    if not fallback_ids:
        fallback_ids = list(chapter_ranked_photo_ids)
    selected: list[str] = []
    for photo_id in fallback_ids:
        if photo_id not in selected:
            selected.append(photo_id)
        if len(selected) == desired_count:
            break
    if not selected and chapter_ranked_photo_ids:
        selected = [chapter_ranked_photo_ids[0]]
    if len(selected) < desired_count and selected:
        selected.extend([selected[-1]] * (desired_count - len(selected)))
    return selected


def pick_opening_photo_ids(
    chapter: ChapterPlanItem,
    chapter_ranked_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
) -> list[str]:
    """为章节开场页选择照片。

    优先使用章节封面图，其次在 must_include、主角优先和质量分之间做平衡。
    """
    if not chapter_ranked_photo_ids:
        return []
    if chapter.cover_photo_id and chapter.cover_photo_id in chapter_ranked_photo_ids:
        return [chapter.cover_photo_id]
    must_include = set(constraints.must_include)
    best_photo_id = max(
        chapter_ranked_photo_ids,
        key=lambda photo_id: (
            1 if photo_id in must_include else 0,
            1 if constraints.hero_person_id and constraints.hero_person_id in photo_lookup[photo_id].person_ids else 0,
            photo_lookup[photo_id].rank_weight,
            -chapter_ranked_photo_ids.index(photo_id),
        ),
    )
    return [best_photo_id]


def pick_hero_photo_ids(
    chapter_ranked_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
    used_photo_ids: set[str],
    previous_page_photo_ids: set[str],
) -> list[str]:
    """为 hero 页选择主视觉照片。"""
    if not chapter_ranked_photo_ids:
        return []
    candidate_ids = [photo_id for photo_id in chapter_ranked_photo_ids if photo_id not in used_photo_ids]
    if not candidate_ids:
        candidate_ids = list(chapter_ranked_photo_ids)
    candidate_ids.sort(
        key=lambda photo_id: (
            1 if constraints.hero_person_id and constraints.hero_person_id in photo_lookup[photo_id].person_ids else 0,
            1 if photo_lookup[photo_id].orientation == "landscape" else 0,
            -len(previous_page_photo_ids & {photo_id}),
            photo_lookup[photo_id].rank_weight,
        ),
        reverse=True,
    )
    return [candidate_ids[0]]


def pick_transition_photo_ids(
    chapter_sequence_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    used_photo_ids: set[str],
    previous_page_photo_ids: set[str],
    prefer_hero: bool,
    constraints: GenerateConstraints,
) -> list[str]:
    """为过渡页选择单图候选。

    过渡页更强调叙事连续性，因此优先从顺序池中选取未使用且不与上一页冲突的图片。
    """
    candidates = [
        photo_id for photo_id in chapter_sequence_photo_ids if photo_id not in used_photo_ids and photo_id not in previous_page_photo_ids
    ]
    if not candidates:
        candidates = [photo_id for photo_id in chapter_sequence_photo_ids if photo_id not in previous_page_photo_ids]
    if not candidates:
        return []
    candidates.sort(
        key=lambda photo_id: (
            1 if prefer_hero and constraints.hero_person_id and constraints.hero_person_id in photo_lookup[photo_id].person_ids else 0,
            int(bool(photo_lookup[photo_id].scene_tags)),
            photo_lookup[photo_id].rank_weight,
        ),
        reverse=True,
    )
    return [candidates[0]]


def pick_detail_photo_ids(
    chapter_ranked_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    used_photo_ids: set[str],
    previous_page_photo_ids: set[str],
    prefer_hero: bool,
    constraints: GenerateConstraints,
) -> list[str]:
    """为 detail 页选择补充型照片。

    该页会适度偏向信息补充和节奏变化，不一味追求最高质量的大图。
    """
    candidates = [
        photo_id for photo_id in chapter_ranked_photo_ids if photo_id not in used_photo_ids and photo_id not in previous_page_photo_ids
    ]
    if not candidates:
        candidates = [photo_id for photo_id in chapter_ranked_photo_ids if photo_id not in previous_page_photo_ids]
    if not candidates:
        return []
    candidates.sort(
        key=lambda photo_id: (
            (3.0 if prefer_hero and constraints.hero_person_id and constraints.hero_person_id in photo_lookup[photo_id].person_ids else 0.0)
            + (1.5 if not photo_lookup[photo_id].is_duplicate else 0.0)
            - abs(photo_lookup[photo_id].rank_weight - 0.55)
        ),
        reverse=True,
    )
    return [candidates[0]]


def story_pair_score(anchor: KeptPhoto, candidate: KeptPhoto) -> float:
    """计算两张照片在叙事拼组上的适配分。"""
    shared_scene_tags = len(set(anchor.scene_tags) & set(candidate.scene_tags))
    shared_people = len(set(anchor.person_ids) & set(candidate.person_ids))
    time_bonus = 0.0
    if anchor.captured_at and candidate.captured_at:
        seconds = abs((anchor.captured_at - candidate.captured_at).total_seconds())
        time_bonus = max(0.0, 3600.0 - min(seconds, 3600.0)) / 3600.0
    orientation_bonus = 0.3 if anchor.orientation != candidate.orientation else 0.0
    duplicate_penalty = 1.0 if candidate.is_duplicate else 0.0
    return (shared_scene_tags * 2.0) + (shared_people * 1.2) + time_bonus + orientation_bonus - duplicate_penalty


def pick_collage_photo_ids(
    chapter_sequence_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    used_photo_ids: set[str],
    previous_page_photo_ids: set[str],
) -> list[str]:
    """为 collage 页选择多图候选。

    该逻辑先确定一张锚点图，再围绕它寻找更像同一段故事的配图。
    """
    desired_count = candidate_count_for_role("collage")
    available_ids = [
        photo_id
        for photo_id in chapter_sequence_photo_ids
        if photo_id not in used_photo_ids and photo_id not in previous_page_photo_ids and not photo_lookup[photo_id].is_duplicate
    ]
    if not available_ids:
        available_ids = [
            photo_id for photo_id in chapter_sequence_photo_ids if photo_id not in used_photo_ids and photo_id not in previous_page_photo_ids
        ]
    if not available_ids:
        available_ids = [photo_id for photo_id in chapter_sequence_photo_ids if photo_id not in previous_page_photo_ids]
    if not available_ids:
        return []

    anchor_id = available_ids[0]
    anchor_photo = photo_lookup[anchor_id]
    selected = [anchor_id]
    remaining_ids = [photo_id for photo_id in available_ids if photo_id != anchor_id]
    remaining_ids.sort(
        key=lambda photo_id: (
            story_pair_score(anchor_photo, photo_lookup[photo_id]),
            photo_lookup[photo_id].rank_weight,
        ),
        reverse=True,
    )
    for photo_id in remaining_ids:
        if photo_id not in selected:
            selected.append(photo_id)
        if len(selected) == desired_count:
            break
    return selected


def pick_summary_photo_ids(
    chapter_sequence_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    used_photo_ids: set[str],
    previous_page_photo_ids: set[str],
    prefer_hero: bool,
    constraints: GenerateConstraints,
) -> list[str]:
    """为 summary 页选择总结性照片组合。"""
    desired_count = candidate_count_for_role("summary")
    candidate_ids = [
        photo_id for photo_id in chapter_sequence_photo_ids if photo_id not in used_photo_ids and photo_id not in previous_page_photo_ids
    ]
    if not candidate_ids:
        candidate_ids = [photo_id for photo_id in chapter_sequence_photo_ids if photo_id not in previous_page_photo_ids]
    if not candidate_ids:
        return []
    candidate_ids.sort(
        key=lambda photo_id: (
            1 if prefer_hero and constraints.hero_person_id and constraints.hero_person_id in photo_lookup[photo_id].person_ids else 0,
            photo_lookup[photo_id].rank_weight,
            int(bool(photo_lookup[photo_id].scene_tags)),
        ),
        reverse=True,
    )
    selected: list[str] = []
    for photo_id in candidate_ids:
        if photo_id not in selected:
            selected.append(photo_id)
        if len(selected) == desired_count:
            break
    return selected


def pick_ending_photo_ids(
    chapter_sequence_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    used_photo_ids: set[str],
    previous_page_photo_ids: set[str],
) -> list[str]:
    """为 ending 页选择收束照片。

    该页更倾向章节尾部的图片，并尽量避免重复图破坏结尾质感。
    """
    desired_count = candidate_count_for_role("ending")
    candidate_ids = [
        photo_id for photo_id in reversed(chapter_sequence_photo_ids) if photo_id not in used_photo_ids and photo_id not in previous_page_photo_ids
    ]
    if not candidate_ids:
        candidate_ids = [photo_id for photo_id in reversed(chapter_sequence_photo_ids) if photo_id not in previous_page_photo_ids]
    if not candidate_ids:
        return []

    selected: list[str] = []
    for photo_id in candidate_ids:
        if photo_lookup[photo_id].is_duplicate and selected:
            continue
        selected.append(photo_id)
        if len(selected) == desired_count:
            break
    return list(reversed(selected))


def pick_candidate_photo_ids(
    role: str,
    chapter: ChapterPlanItem,
    chapter_ranked_photo_ids: list[str],
    chapter_sequence_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    constraints: GenerateConstraints,
    used_photo_ids: set[str],
    previous_page_photo_ids: set[str],
    prefer_hero: bool,
) -> list[str]:
    """按页面角色分发到对应的选图策略。"""
    if role == "chapter_opening":
        selected = pick_opening_photo_ids(
            chapter,
            chapter_ranked_photo_ids,
            photo_lookup,
            constraints,
        )
    elif role == "hero":
        selected = pick_hero_photo_ids(
            chapter_ranked_photo_ids,
            photo_lookup,
            constraints,
            used_photo_ids,
            previous_page_photo_ids,
        )
    elif role == "transition":
        selected = pick_transition_photo_ids(
            chapter_sequence_photo_ids,
            photo_lookup,
            used_photo_ids,
            previous_page_photo_ids,
            prefer_hero,
            constraints,
        )
    elif role == "detail":
        selected = pick_detail_photo_ids(
            chapter_ranked_photo_ids,
            photo_lookup,
            used_photo_ids,
            previous_page_photo_ids,
            prefer_hero,
            constraints,
        )
    elif role == "collage":
        selected = pick_collage_photo_ids(
            chapter_sequence_photo_ids,
            photo_lookup,
            used_photo_ids,
            previous_page_photo_ids,
        )
    elif role == "summary":
        selected = pick_summary_photo_ids(
            chapter_sequence_photo_ids,
            photo_lookup,
            used_photo_ids,
            previous_page_photo_ids,
            prefer_hero,
            constraints,
        )
    else:
        selected = pick_ending_photo_ids(
            chapter_sequence_photo_ids,
            photo_lookup,
            used_photo_ids,
            previous_page_photo_ids,
        )
    if selected:
        return selected
    return pick_fallback_photo_ids(
        chapter_ranked_photo_ids,
        previous_page_photo_ids,
        candidate_count_for_role(role),
    )


def resolve_layout_family(
    role: str,
    candidate_count: int,
    previous_layout_family: str | None,
    is_spread: bool,
    prior_collage_count: int,
) -> str:
    """根据页面角色和候选数量选择版式族。"""
    if is_spread:
        return "spread_full_bleed"
    if role == "chapter_opening":
        return "chapter_cover"
    if role == "hero":
        return "single_full_bleed"
    if role == "transition":
        return "single_full_bleed"
    if role == "detail":
        return "single_full_bleed"
    if role == "collage":
        return "grid_nine" if prior_collage_count % 2 == 0 else "triple_narrative"
    if role == "summary":
        return "double_side_by_side" if candidate_count > 1 else "single_full_bleed"
    if role == "ending" and candidate_count == 1:
        return "single_full_bleed"
    return "double_side_by_side"


def resolve_text_need(role: str) -> str:
    """返回页面需要的文本类型。"""
    return "chapter_title" if role == "chapter_opening" else "none"


def page_contains_hero(
    candidate_photo_ids: list[str],
    photo_lookup: dict[str, KeptPhoto],
    hero_person_id: str | None,
) -> bool:
    """判断当前页面是否包含目标主角。"""
    if hero_person_id is None:
        return False
    return any(hero_person_id in photo_lookup[photo_id].person_ids for photo_id in candidate_photo_ids if photo_id in photo_lookup)


def score_page_plan(
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
            if page_contains_hero(page.candidate_photo_ids, photo_lookup, constraints.hero_person_id):
                hero_focus_photo_score += 0.25
        score += hero_focus_photo_score

    return score
