"""照片清洗引擎 —— 基础逻辑版（不依赖 AI）。

对相册中每张照片进行基础质量评估：
- 从文件元数据提取尺寸、大小信息
- 检测明显异常（文件过小、尺寸异常）
- 生成 quality_score（0-10）和 recommendation（keep / remove）
"""

from typing import Any

# 阈值常量
MIN_FILE_SIZE_BYTES = 10 * 1024       # 10 KB —— 过小可能是缩略图/损坏
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MIN_DIMENSION = 100                     # 最小边长
LOW_RES_THRESHOLD = 800                 # 低于此值视为低分辨率


def analyze_photo_quality(photo_meta: dict[str, Any]) -> dict[str, Any]:
    """分析单张照片的质量并返回评分与标签。

    当前使用基于规则的评估（无需 AI），后续可接入 DeepSeek V4 Pro 增强。

    Returns:
        dict: quality_score（0-10）、tags、recommendation、issues。
    """
    issues: list[str] = []
    tags: list[str] = []
    score = 7.0  # 默认基础分

    file_size = photo_meta.get("size", 0)
    width = photo_meta.get("width") or 0
    height = photo_meta.get("height") or 0
    content_type = photo_meta.get("content_type", "")

    # 文件大小检查
    if file_size < MIN_FILE_SIZE_BYTES:
        issues.append("file_too_small")
        score -= 4.0
    elif file_size < 50 * 1024:
        score -= 1.0
        tags.append("low_size")

    if file_size > MAX_FILE_SIZE_BYTES:
        tags.append("high_resolution")

    # 分辨率检查
    min_side = min(width, height) if width and height else 0
    if min_side > 0 and min_side < MIN_DIMENSION:
        issues.append("resolution_too_low")
        score -= 4.0
    elif 0 < min_side < LOW_RES_THRESHOLD:
        score -= 1.0
        tags.append("low_resolution")

    if width > 3000 or height > 3000:
        tags.append("high_resolution")

    # 格式标签
    if "png" in content_type:
        tags.append("png_format")
    elif "webp" in content_type:
        tags.append("webp_format")

    # 评分钳制
    score = max(0.0, min(10.0, round(score, 1)))

    # 推荐决策
    if score < 3.0:
        recommendation = "remove"
        tags.append("suggest_remove")
    else:
        recommendation = "keep"

    return {
        "photo_id": photo_meta.get("id"),
        "quality_score": score,
        "tags": tags,
        "issues": issues,
        "recommendation": recommendation,
    }


def detect_duplicates(photos: list[dict[str, Any]]) -> list[list[str]]:
    """基于文件大小 + 文件名相似度检测重复组。

    当前为简化实现：相同文件大小且文件名相似的归为一组。
    后续可接入感知哈希（pHash）做精确检测。

    Returns:
        list[list[str]]: 每组重复照片的 ID 列表。
    """
    size_groups: dict[int, list[dict[str, Any]]] = {}
    for p in photos:
        size_groups.setdefault(p.get("size", 0), []).append(p)

    duplicate_groups: list[list[str]] = []
    for group in size_groups.values():
        if len(group) >= 2:
            duplicate_groups.append([p["id"] for p in group])

    return duplicate_groups


def run_cleaning(album_id: str, photo_list: list[dict[str, Any]]) -> dict[str, Any]:
    """对相册的全部照片执行清洗分析。

    Returns:
        dict: summary（总数/建议保留/建议删除/重复组）+ per_photo 详情。
    """
    per_photo: list[dict[str, Any]] = []
    keep_count = 0
    remove_count = 0

    for photo in photo_list:
        result = analyze_photo_quality(photo)
        per_photo.append(result)
        if result["recommendation"] == "keep":
            keep_count += 1
        else:
            remove_count += 1

    duplicates = detect_duplicates(photo_list)

    return {
        "album_id": album_id,
        "summary": {
            "total": len(photo_list),
            "keep": keep_count,
            "remove": remove_count,
            "duplicate_groups": len(duplicates),
        },
        "duplicates": duplicates,
        "per_photo": per_photo,
    }
