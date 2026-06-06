"""章节聚类算法模块。

纯函数实现，不依赖 LangGraph State，可独立测试。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pixelpress_backend.core.enums import SceneMode
from pixelpress_backend.models.workflow_contracts import TimeRange

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CLUSTERING_PIPELINE_VERSION = "1.0.0"

# 场景模式 → 时间间隔阈值（天）
GAP_THRESHOLD_DAYS: dict[SceneMode, int] = {
    SceneMode.ANNUAL: 7,  # 年度册：>7天间隔视为新章节
    SceneMode.EVENT: 2,   # 活动册：>2天间隔视为新章节
}

MIN_PHOTOS_PER_CHAPTER = 3  # 低于此数的章节合并到前一个章节
MAX_CHAPTERS = 20           # 最多章节数

# ---------------------------------------------------------------------------
# 内部数据结构
# ---------------------------------------------------------------------------


@dataclass
class PhotoForClustering:
    """聚类算法内部使用的照片表示。"""

    photo_id: str
    rank_weight: float
    captured_at: datetime | None = None
    # --- Phase 2 新增 ---
    location_cluster: str | None = None       # GPS 聚类标签
    person_ids: list[str] = field(default_factory=list)   # 人脸聚类 ID
    scene_tags: list[str] = field(default_factory=list)   # CLIP 场景标签


@dataclass
class ChapterGroup:
    """聚类算法输出的分组（尚未转为 ChapterPlanItem）。"""

    photos: list[PhotoForClustering]
    time_range: TimeRange | None = None
    degrade_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 公开函数
# ---------------------------------------------------------------------------


def compute_input_hash(
    photo_ids: list[str],
    scene_mode: SceneMode,
    hero_person_id: str | None = None,
) -> str:
    """计算聚类输入哈希（规范 2.3：可重放）。

    相同输入 + 相同 pipeline_version → 相同哈希 → 可验证输出一致性。
    """
    payload = {
        "photo_ids": sorted(photo_ids),
        "scene_mode": scene_mode.value,
        "hero_person_id": hero_person_id or "",
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def cluster_chapters(
    photos: list[PhotoForClustering],
    scene_mode: SceneMode,
    hero_person_id: str | None = None,
) -> list[ChapterGroup]:
    """章节聚类主入口。

    三级降级策略：
    1. 有时间数据 → 时间分组聚类
    2. 部分有时间 → 有时间的分组，无时间的合并到最后一个分组
    3. 完全无时间 → 单章节兜底
    """
    # 过滤掉 rank_weight <= 0 的照片
    active_photos = [p for p in photos if p.rank_weight > 0]

    if not active_photos:
        return []

    # 单张照片：单章节，低置信度标记
    if len(active_photos) == 1:
        return [ChapterGroup(
            photos=active_photos,
            degrade_reasons=["single_photo"],
        )]

    # 判断时间数据可用性
    has_time = [p for p in active_photos if p.captured_at is not None]
    no_time = [p for p in active_photos if p.captured_at is None]

    if not has_time:
        # 降级策略 3：完全无时间 → 单章节兜底
        return [_single_fallback_group(active_photos, reason="no_time_data")]

    # 降级策略 2 或正常策略 1：有时间数据
    groups = _build_time_groups(has_time, scene_mode)

    # 将无时间照片追加到最后一个分组（确定性规则）
    if no_time:
        groups = _merge_no_time_photos(groups, no_time)

    # Phase 2：融合拆分（场景/人物/地点断裂检测）
    # 字段为空时自动跳过，回退到纯时间分组（Phase 1 行为）
    groups = _fusion_split(groups)

    # Phase 2：检查主角人物分布（规范 6.4/13）
    groups = check_hero_person_distribution(groups, hero_person_id)

    # 合并小章节
    groups = _merge_small_groups(groups, MIN_PHOTOS_PER_CHAPTER)

    # 限制最大章节数
    if len(groups) > MAX_CHAPTERS:
        groups = _consolidate_groups(groups, MAX_CHAPTERS)

    return groups


def compute_time_range(photos: list[PhotoForClustering]) -> TimeRange | None:
    """计算分组的时间范围。"""
    times = [p.captured_at for p in photos if p.captured_at is not None]
    if not times:
        return None
    return TimeRange(start=min(times), end=max(times))


def select_cover_photo(photos: list[PhotoForClustering]) -> str | None:
    """选择代表图：rank_weight 最高的照片。

    规则：
    1. 筛选 rank_weight > 0 的照片
    2. 按 rank_weight 降序排列
    3. 返回第一张的 photo_id
    4. 空列表返回 None
    """
    candidates = sorted(
        [p for p in photos if p.rank_weight > 0],
        key=lambda p: p.rank_weight,
        reverse=True,
    )
    return candidates[0].photo_id if candidates else None


def extract_scene_tags(photos: list[PhotoForClustering]) -> list[str]:
    """提取分组内最高频的 scene_tags（取 top-3）。"""
    tag_count: dict[str, int] = {}
    for p in photos:
        for tag in p.scene_tags:
            tag_count[tag] = tag_count.get(tag, 0) + 1
    sorted_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)
    return [tag for tag, _ in sorted_tags[:3]]


def extract_key_persons(photos: list[PhotoForClustering]) -> list[str]:
    """提取分组内出现频次最高的 person_ids（取 top-3）。"""
    person_count: dict[str, int] = {}
    for p in photos:
        for pid in p.person_ids:
            person_count[pid] = person_count.get(pid, 0) + 1
    sorted_persons = sorted(person_count.items(), key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in sorted_persons[:3]]


def check_hero_person_distribution(
    groups: list[ChapterGroup],
    hero_person_id: str | None,
) -> list[ChapterGroup]:
    """检查主角人物在章节中的分布（规范 6.4/13）。

    若主角只集中在 ≤1 个章节，降低所有章节的置信度标记。
    这确保 hero_person_id 约束在聚类层就被考虑。
    """
    if not hero_person_id:
        return groups

    chapters_with_hero = 0
    for group in groups:
        has_hero = any(
            hero_person_id in p.person_ids
            for p in group.photos
        )
        if has_hero:
            chapters_with_hero += 1

    # 主角只出现在 ≤1 个章节 → 标记低置信度
    if chapters_with_hero <= 1 and len(groups) > 1:
        for group in groups:
            group.degrade_reasons.append("hero_person_concentrated")

    return groups


def compute_cluster_confidence(
    group: ChapterGroup,
    scene_mode: SceneMode,  # noqa: ARG001 – 预留给 Phase 2 场景模式权重
) -> float:
    """计算聚类置信度。

    因素：
    1. 时间分布均匀度 (0~1)：标准差/均值越小越均匀
    2. 照片数量合理度 (0~1)：3~50 张满分
    3. 是否有降级 (0/1)：有降级扣分
    """
    photos_with_time = [p for p in group.photos if p.captured_at is not None]

    # 因素1：时间均匀度
    if len(photos_with_time) >= 2:
        times = [p.captured_at.timestamp() for p in photos_with_time]  # type: ignore[union-attr]
        intervals = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        mean_interval = sum(intervals) / len(intervals) if intervals else 0
        if mean_interval > 0:
            std_interval = (sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)) ** 0.5
            uniformity = max(0.0, 1.0 - std_interval / mean_interval)
        else:
            uniformity = 1.0
    else:
        uniformity = 0.5  # 只有1张有时间，信息不足

    # 因素2：数量合理度
    count = len(group.photos)
    if 3 <= count <= 50:
        count_score = 1.0
    elif count < 3:
        count_score = count / 3.0
    else:
        count_score = max(0.5, 50.0 / count)

    # 因素3：降级扣分
    no_degrade = 1.0 if not group.degrade_reasons else 0.5

    confidence = 0.4 * uniformity + 0.3 * count_score + 0.3 * no_degrade
    return round(min(1.0, max(0.0, confidence)), 2)


def generate_chapter_title(
    group: ChapterGroup,
    scene_mode: SceneMode,
    chapter_index: int,
) -> str:
    """生成章节标题（规则式，无 LLM 依赖）。

    优先级：
    1. 有 scene_tags → 用场景标签命名（如"海边时光"）
    2. 有时间范围 → annual: "2026年·五月时光" / event: "精彩瞬间·一"
    3. 无时间 → "第N章"
    """
    # 优先级1：有 scene_tags → 用场景标签命名
    scene_tags = extract_scene_tags(group.photos)
    if scene_tags:
        tag = scene_tags[0]
        TAG_NAMES: dict[str, str] = {
            "beach": "海边", "snow": "雪地", "birthday": "生日",
            "sunset": "日落", "dinner": "聚餐", "ceremony": "典礼",
            "travel": "旅途", "party": "派对", "wedding": "婚礼",
            "graduation": "毕业", "festival": "节日", "nature": "自然",
        }
        name = TAG_NAMES.get(tag, tag)
        return f"{name}时光"

    time_range = compute_time_range(group.photos)

    if time_range and time_range.start is not None and scene_mode == SceneMode.ANNUAL:
        # 年度册：用月份命名
        # 取照片数量最多的月份（而非简单取 start.month）
        month_names = [
            "一月", "二月", "三月", "四月", "五月", "六月",
            "七月", "八月", "九月", "十月", "十一月", "十二月",
        ]
        month_counts: dict[int, int] = {}
        for p in group.photos:
            if p.captured_at is not None:
                m = p.captured_at.month
                month_counts[m] = month_counts.get(m, 0) + 1
        if month_counts:
            dominant_month = max(month_counts, key=month_counts.get)  # type: ignore[arg-type]
            year = time_range.start.year
            return f"{year}年·{month_names[dominant_month - 1]}时光"
        # 无时间数据时回退到 start.month
        month_index = time_range.start.month - 1
        year = time_range.start.year
        return f"{year}年·{month_names[month_index]}时光"

    if scene_mode == SceneMode.EVENT:
        # 活动册：序号命名
        ordinal = [
            "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
        ]
        idx = min(chapter_index, len(ordinal) - 1)
        return f"精彩瞬间·{ordinal[idx]}"

    # 兜底
    return f"第{chapter_index + 1}章"


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------


def _build_time_groups(
    photos: list[PhotoForClustering],
    scene_mode: SceneMode,
) -> list[ChapterGroup]:
    """按时间间隔分组。

    步骤：
    1. 按 captured_at 升序排列
    2. 计算相邻照片的时间间隔
    3. gap > 阈值时切新章节
    4. 为每个分组计算 time_range
    """
    sorted_photos = sorted(photos, key=lambda p: p.captured_at)  # type: ignore[arg-type]
    threshold_days = GAP_THRESHOLD_DAYS[scene_mode]
    threshold = timedelta(days=threshold_days)

    groups: list[ChapterGroup] = []
    current_photos = [sorted_photos[0]]

    for i in range(1, len(sorted_photos)):
        gap = sorted_photos[i].captured_at - sorted_photos[i - 1].captured_at  # type: ignore[operator]
        if gap > threshold:
            groups.append(ChapterGroup(photos=current_photos))
            current_photos = [sorted_photos[i]]
        else:
            current_photos.append(sorted_photos[i])

    groups.append(ChapterGroup(photos=current_photos))

    # 为每个分组计算 time_range（避免后续重复遍历）
    for group in groups:
        group.time_range = compute_time_range(group.photos)

    return groups


def _merge_no_time_photos(
    groups: list[ChapterGroup],
    no_time_photos: list[PhotoForClustering],
) -> list[ChapterGroup]:
    """将无时间照片追加到最后一个分组（确定性规则）。

    合并方向：追加到最后一个分组。
    原因：无时间照片无法确定排序位置，追加到最后一个分组是最确定性的选择，
    避免了"前一个"在遍历过程中语义变化的问题。
    若无任何分组，则创建单章节兜底。
    """
    if not groups:
        return [_single_fallback_group(no_time_photos, reason="no_time_data")]

    groups[-1].photos.extend(no_time_photos)
    groups[-1].degrade_reasons.append("partial_time_data")
    # 重新计算 time_range（无时间照片不影响时间范围，但保持一致性）
    groups[-1].time_range = compute_time_range(groups[-1].photos)
    return groups


def _merge_small_groups(
    groups: list[ChapterGroup],
    min_photos: int,
) -> list[ChapterGroup]:
    """合并照片数 < min_photos 的章节到前一个章节。

    合并方向：向前合并（合并到前一个章节），保证确定性。
    第一个章节若太小，合并到下一个章节。
    """
    if len(groups) <= 1:
        return groups

    merged: list[ChapterGroup] = [groups[0]]
    for group in groups[1:]:
        if len(group.photos) < min_photos and merged:
            # 向前合并
            merged[-1].photos.extend(group.photos)
            merged[-1].degrade_reasons.append("merged_small_chapter")
        else:
            merged.append(group)

    # 处理第一个章节太小的情况：合并到第二个
    if merged and len(merged) > 1 and len(merged[0].photos) < min_photos:
        merged[1].photos = merged[0].photos + merged[1].photos
        merged[1].degrade_reasons.append("merged_small_chapter")
        merged = merged[1:]

    # 重新计算受影响分组的 time_range
    for group in merged:
        group.time_range = compute_time_range(group.photos)

    return merged


def _consolidate_groups(
    groups: list[ChapterGroup],
    max_count: int,
) -> list[ChapterGroup]:
    """章节数超过上限时，合并照片数最少的相邻章节对。

    策略：每次找到照片总数最小的相邻章节对进行合并，
    而非总是合并末尾，避免最后一个章节异常庞大。
    """
    while len(groups) > max_count:
        # 找到照片数之和最小的相邻章节对
        min_pair_idx = 0
        min_pair_size = len(groups[0].photos) + len(groups[1].photos)
        for i in range(1, len(groups) - 1):
            pair_size = len(groups[i].photos) + len(groups[i + 1].photos)
            if pair_size < min_pair_size:
                min_pair_size = pair_size
                min_pair_idx = i
        # 合并该对
        groups[min_pair_idx].photos.extend(groups[min_pair_idx + 1].photos)
        groups[min_pair_idx].degrade_reasons.append("consolidated_oversized")
        # 重新计算 time_range
        groups[min_pair_idx].time_range = compute_time_range(groups[min_pair_idx].photos)
        groups.pop(min_pair_idx + 1)
    return groups


def _single_fallback_group(
    photos: list[PhotoForClustering],
    reason: str,
) -> ChapterGroup:
    """降级为单章节兜底。"""
    group = ChapterGroup(
        photos=photos,
        degrade_reasons=[reason],
    )
    group.time_range = compute_time_range(photos)
    return group


def _fusion_split(groups: list[ChapterGroup]) -> list[ChapterGroup]:
    """Phase 2：按场景/人物/地点信号拆分时间分组。

    对每个时间分组，检查内部是否存在场景断裂、人物断裂或地点断裂。
    若断裂存在且两侧子组 >= MIN_PHOTOS_PER_CHAPTER，则拆分为两个章节。
    字段为空时自动跳过，回退到纯时间分组行为。
    """
    if len(groups) <= 1:
        return groups

    result: list[ChapterGroup] = []
    for group in groups:
        sub_groups = _split_by_signal(group.photos)
        # 如果没有有效的融合信号，不拆分
        if len(sub_groups) <= 1:
            result.append(group)
            continue

        # 为每个子组创建 ChapterGroup
        for sg in sub_groups:
            sg_group = ChapterGroup(photos=sg)
            sg_group.time_range = compute_time_range(sg)
            result.append(sg_group)

    # 合并后可能产生小于阈值的分组，再次合并
    if len(result) > len(groups):
        result = _merge_small_groups(result, MIN_PHOTOS_PER_CHAPTER)

    return result


def _split_by_signal(photos: list[PhotoForClustering]) -> list[list[PhotoForClustering]]:
    """按场景/人物/地点信号拆分照片列表。

    优先级：场景断裂 > 人物断裂 > 地点断裂
    只有两侧都 >= MIN_PHOTOS_PER_CHAPTER 时才拆分。
    """
    # 检查是否有足够的信号数据
    has_scene_tags = any(p.scene_tags for p in photos)
    has_person_ids = any(p.person_ids for p in photos)
    has_location = any(p.location_cluster is not None for p in photos)

    if not (has_scene_tags or has_person_ids or has_location):
        return [photos]  # 无信号数据，不拆分

    # 尝试按场景标签拆分
    if has_scene_tags:
        split = _split_by_tag_change(photos, lambda p: tuple(sorted(p.scene_tags)) if p.scene_tags else None)
        if len(split) > 1 and all(len(s) >= MIN_PHOTOS_PER_CHAPTER for s in split):
            return split

    # 尝试按人物组合拆分
    if has_person_ids:
        split = _split_by_tag_change(photos, lambda p: tuple(sorted(p.person_ids)) if p.person_ids else None)
        if len(split) > 1 and all(len(s) >= MIN_PHOTOS_PER_CHAPTER for s in split):
            return split

    # 尝试按地点拆分
    if has_location:
        split = _split_by_tag_change(photos, lambda p: p.location_cluster)
        if len(split) > 1 and all(len(s) >= MIN_PHOTOS_PER_CHAPTER for s in split):
            return split

    return [photos]


def _split_by_tag_change(
    photos: list[PhotoForClustering],
    key_fn: callable,
) -> list[list[PhotoForClustering]]:
    """当标签 key 变化时拆分分组。"""
    if len(photos) < 2:
        return [photos]

    groups: list[list[PhotoForClustering]] = []
    current = [photos[0]]
    prev_key = key_fn(photos[0])

    for i in range(1, len(photos)):
        curr_key = key_fn(photos[i])
        if curr_key != prev_key and curr_key is not None and prev_key is not None:
            groups.append(current)
            current = [photos[i]]
        else:
            current.append(photos[i])
        prev_key = curr_key

    groups.append(current)
    return groups
