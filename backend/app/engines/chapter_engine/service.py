"""章节聚类引擎 —— 基础逻辑版（不依赖 AI）。

按拍摄时间对照片进行分组：
- 如果照片之间有超过 N 天的时间间隔，则在此处切分章节
- 同一时间段内的照片归入同一章节
- 自动为每个章节生成命名建议
"""

from datetime import datetime, timedelta
from typing import Any

# 默认时间间隔阈值（天）：两张照片间隔超过此天数则切分新章节
DEFAULT_GAP_DAYS = 30


def _parse_datetime(value: Any) -> datetime | None:
    """尝试解析多种格式的时间字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%Y:%m:%d %H:%M:%S",
    ]:
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def cluster_photos(
    photos: list[dict[str, Any]],
    strategy: str = "time_based",
    gap_days: int = DEFAULT_GAP_DAYS,
) -> list[dict[str, Any]]:
    """对照片列表按时间间隔聚类，生成章节结构。

    Args:
        photos: 照片元数据列表（每项包含 id、filename、uploaded_at 等）。
        strategy: 聚类策略（time_based / one_chapter）。
        gap_days: 时间间隔阈值（天）。

    Returns:
        list[dict]: 章节列表，每章包含 name、photo_ids、time_range。
    """
    if not photos:
        return []

    # 单章节模式
    if strategy == "one_chapter" or len(photos) <= 3:
        return [{
            "name": "全部照片",
            "photo_ids": [p["id"] for p in photos],
            "time_range": _time_range_label(photos),
            "photo_count": len(photos),
        }]

    # 时间聚类模式
    # 1. 解析每张照片的时间
    timed_photos: list[tuple[datetime, dict[str, Any]]] = []
    untimed_photos: list[dict[str, Any]] = []
    for p in photos:
        dt = _parse_datetime(p.get("taken_at") or p.get("uploaded_at"))
        if dt:
            timed_photos.append((dt, p))
        else:
            untimed_photos.append(p)

    # 2. 按时间排序
    timed_photos.sort(key=lambda x: x[0])

    # 3. 按时间间隔切分
    if not timed_photos:
        # 全部无时间信息 → 单章
        return [{
            "name": "全部照片",
            "photo_ids": [p["id"] for p in photos],
            "time_range": "未知时间",
            "photo_count": len(photos),
        }]

    threshold = timedelta(days=gap_days)
    groups: list[list[tuple[datetime, dict[str, Any]]]] = []
    current_group: list[tuple[datetime, dict[str, Any]]] = [timed_photos[0]]

    for i in range(1, len(timed_photos)):
        prev_dt = timed_photos[i - 1][0]
        curr_dt = timed_photos[i][0]
        if curr_dt - prev_dt > threshold:
            groups.append(current_group)
            current_group = []
        current_group.append(timed_photos[i])
    groups.append(current_group)

    # 4. 将无时间照片追加到最后一个组
    if untimed_photos and groups:
        for p in untimed_photos:
            groups[-1].append((datetime.min, p))

    # 5. 生成章节
    chapters: list[dict[str, Any]] = []
    for idx, group in enumerate(groups, 1):
        group_photos = [item[1] for item in group]
        chapters.append({
            "name": suggest_chapter_name(group_photos, idx),
            "photo_ids": [p["id"] for p in group_photos],
            "time_range": _time_range_label(group_photos),
            "photo_count": len(group_photos),
        })

    return chapters


def suggest_chapter_name(photos: list[dict[str, Any]], index: int = 1) -> str:
    """基于照片时间范围和数量建议章节名称。

    当前为规则式（无需 AI），后续可接入 Claude API 做语义命名。
    """
    time_label = _time_range_label(photos)
    if time_label and time_label != "未知时间":
        # 例如 "2024年10月"
        return f"第{index}章 · {time_label}"
    return f"第{index}章"


def _time_range_label(photos: list[dict[str, Any]]) -> str:
    """生成照片集的时间范围标签。"""
    datetimes: list[datetime] = []
    for p in photos:
        dt = _parse_datetime(p.get("taken_at") or p.get("uploaded_at"))
        if dt and dt != datetime.min:
            datetimes.append(dt)

    if not datetimes:
        return "未知时间"

    earliest = min(datetimes)
    latest = max(datetimes)
    if earliest.year == latest.year and earliest.month == latest.month:
        return f"{earliest.year}年{earliest.month}月"
    elif earliest.year == latest.year:
        return f"{earliest.year}年{earliest.month}-{latest.month}月"
    else:
        return f"{earliest.year}-{latest.year}"
