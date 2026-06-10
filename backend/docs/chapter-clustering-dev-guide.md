# 第2层 章节聚类节点 — 开发文档

> 版本：v1.0 | 状态：draft | 负责人：B（AI算法工程师）
> 关联规范：项目开发规范.md、AI自动排版系统设计方案-v2.md 第 2.5 节

---

## 目录

1. [节点定位与边界](#1-节点定位与边界)
2. [Phase 0：跑通 Demo（最小可验证闭环）](#2-phase-0跑通-demo最小可验证闭环)
3. [Phase 1：时间分组聚类](#3-phase-1时间分组聚类)
4. [Phase 2：多信号融合与降级策略](#4-phase-2多信号融合与降级策略)
5. [Phase 3：完整功能与生产就绪](#5-phase-3完整功能与生产就绪)
6. [契约变更清单](#6-契约变更清单)
7. [测试计划](#7-测试计划)
8. [与上下游的协作协议](#8-与上下游的协作协议)

---

## 1. 节点定位与边界

### 1.1 在五层流水线中的位置

```
第1层 照片清洗 → [第2层 章节聚类] → 第3层 页面规划 → 第4层 版式生成 → 第5层 全书评分
```

### 1.2 职责定义

| 维度 | 说明 |
|------|------|
| **做** | 将清洗后的照片按时间/场景/人物切分为多个章节，输出结构化的 `ChapterPlan` |
| **不做** | 不决定页数、不生成几何布局、不写数据库、不改任务状态 |
| **上游依赖** | `CleanedPhotoSet`（来自照片清洗层）+ `scene_mode`（来自请求）+ `constraints.hero_person_id`（来自请求） |
| **下游消费者** | 第3层页面规划（消费 `ChapterPlan`）、第5层评分（消费 `ChapterPlan`）、`finalize_node`（写入 `BookLayout.chapters`） |

### 1.3 禁止事项（来自项目开发规范）

- 不回写 `state.cleaned_photo_set`
- 不直接生成页面级结构
- 不改任务状态或布局版本
- 不写数据库或对象存储
- 不跨层消费未声明的内部字段
- 不在关键字段缺失时静默继续

---

## 2. Phase 0：跑通 Demo（最小可验证闭环）

> 目标：用最少的改动让端到端流程跑通，验证五层流水线骨架可运行。
> 不要求聚类质量，只要求输出结构正确、不报错。

### 2.1 当前状态

当前 `chapter_clustering_node.py` 已有占位逻辑：

```python
# 把所有照片扔进一个章节，标题"待实现章节聚类"
chapter_plan = ChapterPlan(
    album_id=node_input.album_id,
    chapters=[
        ChapterPlanItem(
            chapter_id="chapter-001",
            order=1,
            title_candidate="待实现章节聚类",
            photo_ids=photo_ids,
        )
    ],
)
```

**这个占位逻辑已经能跑通全流程。** Phase 0 不需要改任何代码。

### 2.2 Phase 0 验证步骤

```bash
# 1. 安装依赖
cd backend && uv sync

# 2. 跑现有测试
uv run pytest tests/graph/test_chapter_clustering_node.py -v

# 3. 跑全量测试
uv run pytest -v

# 4. 启动服务并手动调用 API
uv run uvicorn pixelpress_backend.main:app --reload

# 5. 用 curl 触发排版生成
curl -X POST http://localhost:8000/api/v1/layouts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "album_id": "demo-album",
    "idempotency_key": "demo-001",
    "scene_mode": "annual",
    "photo_ids": ["p1","p2","p3","p4","p5"],
    "constraints": {"min_pages": 1, "max_pages": 10}
  }'
```

### 2.3 Phase 0 交付标准

- [ ] 全量测试通过（17 个）
- [ ] API 调用返回 `task_status: completed`
- [ ] 返回的 `BookLayout.chapters` 包含 1 个章节，含全部 photo_ids

---

## 3. Phase 1：时间分组聚类

> 目标：实现基于拍摄时间的真实聚类逻辑，使年度册按月份/事件册按天分组。
> 这是第一个有实际业务价值的版本。

### 3.1 前置：确认 `KeptPhoto` 现有字段

远程代码已扩展 `KeptPhoto`，包含聚类所需的全部信号字段，**无需再修改**。

**当前 `KeptPhoto` 字段**（`models/workflow_contracts.py`）：

```python
class KeptPhoto(BaseSchema):
    photo_id: str
    decision: Literal["keep", "deprioritize", "drop"] = "keep"
    rank_weight: float = 1.0
    quality_score: float | None = None          # 质量评分
    duplicate_score: float | None = None        # 重复评分
    saliency_score: float | None = None         # 显著性评分
    face_integrity_score: float | None = None   # 人脸完整性评分
    drop_reason: str | None = None              # 剔除原因
    captured_at: datetime | None = None         # EXIF 拍摄时间 ← Phase 1 核心字段
    location_cluster: str | None = None         # GPS 聚类标签 ← Phase 2 使用
    embedding_ref: str | None = None            # Embedding 引用 ← Phase 2 使用
    person_ids: list[str] = Field(default_factory=list)   # 人脸聚类 ID ← Phase 2 使用
    scene_tags: list[str] = Field(default_factory=list)   # CLIP 场景标签 ← Phase 2 使用
    orientation: str | None = None              # 横竖方向
    is_duplicate: bool = False                  # 是否重复
```

**兼容性确认**：

| 下游消费者 | 是否受影响 | 说明 |
|-----------|-----------|------|
| `chapter_clustering_node` | 是（本节点，主动消费 `captured_at`） | Phase 1 只读 `captured_at`，Phase 2 扩展读 `person_ids`/`scene_tags`/`location_cluster` |
| `pagination_planning_node` | 否 | 只消费 `valid_photos` 列表长度和 `rank_weight`，不读新字段 |
| `layout_generation_node` | 否 | 不直接消费 `KeptPhoto` |
| `book_scoring_node` | 否 | 不直接消费 `KeptPhoto` |
| `finalize_node` | 否 | 通过 `state.chapter_plan` 间接消费，不直接读 `KeptPhoto` |
| `test_conftest.py` | 需更新 | `cleaned_photo_set_fixture` 需补充 `captured_at` 示例数据 |

> 所有字段都有默认值，现有代码无需修改即可运行，**向后兼容**。

### 3.2 前置：扩展 `ChapterPlanItem` 字段

远程代码已定义 `TimeRange`、`ClusteringSummary`、`ChapterPlan.clustering_summary`，大部分字段已存在，**只需新增 `degrade_reasons`**。

**已存在的字段**（`models/workflow_contracts.py`）：

```python
class TimeRange(BaseSchema):
    start: datetime | None = None   # 可为 None（无时间数据时）
    end: datetime | None = None

class ChapterPlanItem(BaseSchema):
    chapter_id: str
    order: int
    title_candidate: str
    photo_ids: list[str] = Field(default_factory=list)
    cover_photo_id: str | None = None          # ✅ 已存在
    key_person_ids: list[str] = Field(default_factory=list)  # ✅ 已存在
    scene_tags: list[str] = Field(default_factory=list)      # ✅ 已存在
    time_range: TimeRange = Field(default_factory=TimeRange) # ✅ 已存在
    cluster_confidence: float | None = None    # ✅ 已存在（None=未评估）

class ClusteringSummary(BaseSchema):           # ✅ 已存在
    chapter_count: int = 0
    avg_photos_per_chapter: int = 0
    low_confidence_chapters: list[str] = Field(default_factory=list)

class ChapterPlan(BaseSchema):
    album_id: str
    chapters: list[ChapterPlanItem] = Field(default_factory=list)
    clustering_summary: ClusteringSummary = Field(default_factory=ClusteringSummary)  # ✅ 已存在
```

**Phase 1 需新增的字段**：

```python
class ChapterPlanItem(BaseSchema):
    # ... 已有字段 ...
    # --- Phase 1 新增 ---
    degrade_reasons: list[str] = Field(default_factory=list)  # 降级原因（规范 9.1）
```

**兼容性分析**：

| 下游消费者 | 是否受影响 | 说明 |
|-----------|-----------|------|
| `pagination_planning_node` | 否 | 只读 `chapter_id`、`photo_ids`、`order` |
| `book_scoring_node` | 是 | 可消费 `cluster_confidence` 和 `degrade_reasons` 辅助评分（Phase 2 再用） |
| `finalize_node` | 是 | `chapters` 字段会写入 `BookLayout.chapters`，新字段自动序列化到 JSON |

**`finalize_node` 影响**：当前 `finalize_node` 用 `state.chapter_plan.model_dump()["chapters"]` 写入 `BookLayout.chapters`，新增字段会自动包含在 dump 结果中，无需改代码。但需确认 `BookLayout.chapters` 的下游消费者（前端、评分层）能容忍新字段。由于 `BaseSchema` 配置了 `extra="forbid"`，`BookLayout.chapters` 类型为 `list[JSONDict]`，新字段会作为 JSON 的一部分透传，**无兼容性问题**。

### 3.3 前置：确认 `ChapterClusteringInput`

远程代码已定义 `ChapterClusteringInput`，**无需修改**。

**当前定义**（`models/workflow_contracts.py`）：

```python
class ChapterClusteringInput(BaseSchema):
    album_id: str
    scene_mode: SceneMode
    valid_photos: list[KeptPhoto] = Field(default_factory=list)    # 直接传照片列表
    constraints: GenerateConstraints = Field(default_factory=GenerateConstraints)  # 完整约束对象
```

**关键说明**：

- `valid_photos` 直接传 `list[KeptPhoto]`（而非 `CleanedPhotoSet`），与远程节点代码一致
- `hero_person_id` 和 `chapter_count_hint` 从 `constraints` 中读取：
  - `constraints.hero_person_id` → 主角人物 ID（规范 6.4/13）
  - `constraints.chapter_count_hint` → 章节数软约束

### 3.4 新建算法模块

**新建文件**：`algorithms/__init__.py`、`algorithms/chapter_clustering.py`

```
src/pixelpress_backend/
├── algorithms/                  ← 新建
│   ├── __init__.py
│   └── chapter_clustering.py    ← 聚类算法（纯函数，不依赖 LangGraph State）
├── graph/
│   └── chapter_clustering_node.py  ← 只做 State ↔ 契约转换，调 algorithms
```

**设计理由**：
- 设计方案 2.5 节要求"每个节点都可以是纯函数式节点"
- 将算法抽离后，`graph/` 下节点文件只负责 `state → 契约对象 → 调 algorithm → 写回 state`
- 算法函数可独立测试，不需要构造 `LayoutWorkflowState`

### 3.5 算法实现：`algorithms/chapter_clustering.py`

#### 3.5.1 数据结构

```python
@dataclass
class PhotoForClustering:
    """聚类算法内部使用的照片表示"""
    photo_id: str
    rank_weight: float
    captured_at: datetime | None = None


@dataclass
class ChapterGroup:
    """聚类算法输出的分组（尚未转为 ChapterPlanItem）"""
    photos: list[PhotoForClustering]
    time_range: TimeRange | None = None
    degrade_reasons: list[str] = field(default_factory=list)
```

#### 3.5.2 核心函数

```python
import hashlib
import json

CLUSTERING_PIPELINE_VERSION = "1.0.0"

# 场景模式 → 时间间隔阈值
GAP_THRESHOLD_DAYS = {
    SceneMode.ANNUAL: 7,   # 年度册：>7天间隔视为新章节
    SceneMode.EVENT: 2,    # 活动册：>2天间隔视为新章节
}

MIN_PHOTOS_PER_CHAPTER = 3   # 低于此数的章节合并到前一个章节
MAX_CHAPTERS = 20            # 最多章节数


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
    2. 部分有时间 → 有时间的分组，无时间的合并到前一个分组
    3. 完全无时间 → 单章节兜底

    Args:
        photos: 清洗后的有效照片列表
        scene_mode: 场景模式（annual/event）
        hero_person_id: 主角人物 ID（Phase 2 使用）

    Returns:
        分组列表，每组包含照片、时间范围、降级原因
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

    # 合并小章节
    groups = _merge_small_groups(groups, MIN_PHOTOS_PER_CHAPTER)

    # 限制最大章节数
    if len(groups) > MAX_CHAPTERS:
        groups = _consolidate_groups(groups, MAX_CHAPTERS)

    return groups


def _build_time_groups(
    photos: list[PhotoForClustering],
    scene_mode: SceneMode,
) -> list[ChapterGroup]:
    """按时间间隔分组。

    步骤：
    1. 按 captured_at 升序排列
    2. 计算相邻照片的时间间隔
    3. gap > 阈值时切新章节
    """
    sorted_photos = sorted(photos, key=lambda p: p.captured_at)
    threshold_days = GAP_THRESHOLD_DAYS[scene_mode]
    threshold = timedelta(days=threshold_days)

    groups: list[ChapterGroup] = []
    current_photos = [sorted_photos[0]]

    for i in range(1, len(sorted_photos)):
        gap = sorted_photos[i].captured_at - sorted_photos[i - 1].captured_at
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
    return ChapterGroup(
        photos=photos,
        degrade_reasons=[reason],
    )


def compute_time_range(photos: list[PhotoForClustering]) -> TimeRange | None:
    """计算分组的时间范围。"""
    times = [p.captured_at for p in photos if p.captured_at is not None]
    if not times:
        return None
    return TimeRange(start=min(times), end=max(times))


def select_cover_photo(photos: list[PhotoForClustering]) -> str | None:
    """选择代表图：rank_weight 最高且 decision 为 keep 的照片。

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


def compute_cluster_confidence(
    group: ChapterGroup,
    scene_mode: SceneMode,
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
        times = [p.captured_at.timestamp() for p in photos_with_time]
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
    1. 有时间范围 → annual: "2026年·五月时光" / event: "精彩瞬间·一"
    2. 无时间 → "第N章"
    """
    time_range = compute_time_range(group.photos)

    if time_range and scene_mode == SceneMode.ANNUAL:
        # 年度册：用月份命名
        # 取照片数量最多的月份（而非简单取 start.month）
        # 原因：跨月章节（如5月28日~6月3日）应取照片更集中的月份
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
        ordinal = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
                    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]
        idx = min(chapter_index, len(ordinal) - 1)
        return f"精彩瞬间·{ordinal[idx]}"

    # 兜底
    return f"第{chapter_index + 1}章"
```

### 3.6 修改节点文件：`graph/chapter_clustering_node.py`

```python
from __future__ import annotations

from pixelpress_backend.algorithms.chapter_clustering import (
    CLUSTERING_PIPELINE_VERSION,
    ChapterGroup,
    PhotoForClustering,
    cluster_chapters,
    compute_cluster_confidence,
    compute_input_hash,
    compute_time_range,
    generate_chapter_title,
    select_cover_photo,
)
from pixelpress_backend.models.workflow_contracts import (
    ChapterClusteringInput,
    ChapterPlan,
    ChapterPlanItem,
    ClusteringSummary,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def chapter_clustering_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    # 1. 构建输入（与远程代码一致：valid_photos + constraints）
    node_input = ChapterClusteringInput(
        album_id=state.request.album_id,
        scene_mode=state.request.scene_mode,
        valid_photos=state.cleaned_photo_set.valid_photos if state.cleaned_photo_set else [],
        constraints=state.request.constraints,
    )

    # 2. 从 constraints 中提取约束参数
    hero_person_id = node_input.constraints.hero_person_id
    chapter_count_hint = node_input.constraints.chapter_count_hint

    # 3. 转换为算法内部数据结构
    photos_for_clustering = [
        PhotoForClustering(
            photo_id=p.photo_id,
            rank_weight=p.rank_weight,
            captured_at=p.captured_at,
        )
        for p in node_input.valid_photos
    ]

    # 4. 调用算法
    groups = cluster_chapters(
        photos=photos_for_clustering,
        scene_mode=node_input.scene_mode,
        hero_person_id=hero_person_id,
    )

    # 5. 转换为契约输出
    chapters: list[ChapterPlanItem] = []
    for i, group in enumerate(groups):
        chapters.append(ChapterPlanItem(
            chapter_id=f"chapter-{i + 1:03d}",
            order=i + 1,
            title_candidate=generate_chapter_title(group, node_input.scene_mode, i),
            photo_ids=[p.photo_id for p in group.photos],
            cover_photo_id=select_cover_photo(group.photos),
            time_range=group.time_range,  # 已在 _build_time_groups 中计算
            cluster_confidence=compute_cluster_confidence(group, node_input.scene_mode),
            degrade_reasons=group.degrade_reasons,
        ))

    # 6. 计算 ClusteringSummary
    low_conf = [c.chapter_id for c in chapters if c.cluster_confidence is not None and c.cluster_confidence < 0.5]
    avg_photos = len(photos_for_clustering) // len(chapters) if chapters else 0

    # 7. 写回 state
    state.chapter_plan = ChapterPlan(
        album_id=node_input.album_id,
        chapters=chapters,
        clustering_summary=ClusteringSummary(
            chapter_count=len(chapters),
            avg_photos_per_chapter=avg_photos,
            low_confidence_chapters=low_conf,
        ),
    )

    # 8. 记录算法版本和输入哈希到 metadata（规范 2.3：可重放）
    state.metadata["chapter_clustering_version"] = CLUSTERING_PIPELINE_VERSION
    state.metadata["chapter_clustering_input_hash"] = compute_input_hash(
        photo_ids=[p.photo_id for p in photos_for_clustering],
        scene_mode=node_input.scene_mode,
        hero_person_id=hero_person_id,
    )

    return state
```

### 3.7 Phase 1 验证步骤

```bash
# 1. 跑算法单元测试
uv run pytest tests/algorithms/test_chapter_clustering.py -v

# 2. 跑节点集成测试
uv run pytest tests/graph/test_chapter_clustering_node.py -v

# 3. 跑全量测试（确保没有破坏其他节点）
uv run pytest -v

# 4. API 端到端验证
curl -X POST http://localhost:8000/api/v1/layouts/generate \
  -H "Content-Type: application/json" \
  -d '{
    "album_id": "phase1-test",
    "idempotency_key": "phase1-001",
    "scene_mode": "annual",
    "photo_ids": ["p1","p2","p3","p4","p5","p6","p7","p8","p9","p10"],
    "constraints": {"min_pages": 5, "max_pages": 20}
  }'
```

### 3.8 Phase 1 交付标准

- [ ] 有时间数据时，按时间间隔正确切分多章节
- [ ] 无时间数据时，降级为单章节，`degrade_reasons` 包含 `"no_time_data"`
- [ ] 小章节（<3张）自动合并到前一个章节
- [ ] 每个章节有 `cover_photo_id`（rank_weight 最高的照片）
- [ ] 每个章节有 `cluster_confidence`（0.0~1.0）
- [ ] 年度册标题格式为 "2026年·五月时光"
- [ ] 活动册标题格式为 "精彩瞬间·一"
- [ ] `state.metadata` 中记录了 `chapter_clustering_version`
- [ ] 全量测试通过
- [ ] 现有测试（test_chapter_clustering_node_uses_cleaned_photo_set）仍然通过

---

## 4. Phase 2：多信号融合与降级策略

> 目标：融合场景标签、人物共现等信号，提升聚类质量。
> 依赖：照片清洗层/特征提取层已填充 `KeptPhoto` 的 `person_ids`、`scene_tags`、`location_cluster` 字段。

### 4.1 确认 `KeptPhoto` Phase 2 字段

远程代码已包含 Phase 2 所需的全部字段，**无需修改**：

```python
class KeptPhoto(BaseSchema):
    # ... Phase 1 已使用的字段 ...
    # --- Phase 2 将使用的字段（已存在） ---
    location_cluster: str | None = None       # GPS 聚类标签
    person_ids: list[str] = Field(default_factory=list)  # 人脸聚类 ID
    scene_tags: list[str] = Field(default_factory=list)  # CLIP 场景标签
```

### 4.2 确认 `ChapterPlanItem` Phase 2 字段

远程代码已包含 Phase 2 所需的全部字段，**无需修改**：

```python
class ChapterPlanItem(BaseSchema):
    # ... Phase 1 已使用的字段 ...
    # --- Phase 2 将使用的字段（已存在） ---
    key_person_ids: list[str] = Field(default_factory=list)  # 本章节核心人物
    scene_tags: list[str] = Field(default_factory=list)      # 本章节场景标签
```

### 4.3 扩展算法内部数据结构

```python
@dataclass
class PhotoForClustering:
    photo_id: str
    rank_weight: float
    captured_at: datetime | None = None
    # --- Phase 2 新增 ---
    location_cluster: str | None = None
    person_ids: list[str] = field(default_factory=list)
    scene_tags: list[str] = field(default_factory=list)
```

### 4.4 融合聚类策略

```
优先级1: 时间 + 场景 + 人物 + 地点融合聚类
   ↓ 字段不全时降级
优先级2: 纯时间分组聚类（Phase 1 已实现）
   ↓ 完全没有时间时降级
优先级3: 按数量做简易分桶（Phase 1 已实现）
```

**融合逻辑**：

1. 先按时间分组（复用 Phase 1 的 `_build_time_groups`）
2. 对每个时间分组，检查内部是否存在**场景断裂**（同一组内 scene_tags 差异大 → 拆分）
3. 检查是否存在**人物组合断裂**（同一组内 person_ids 集合差异大 → 拆分）
4. 检查是否存在**地点断裂**（location_cluster 突变 → 拆分）
5. 合并过小的子组

**场景标签提取**：

```python
def extract_scene_tags(photos: list[PhotoForClustering]) -> list[str]:
    """提取分组内最高频的 scene_tags（取 top-3）。"""
    tag_count: dict[str, int] = {}
    for p in photos:
        for tag in p.scene_tags:
            tag_count[tag] = tag_count.get(tag, 0) + 1
    sorted_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)
    return [tag for tag, _ in sorted_tags[:3]]
```

**核心人物提取**：

```python
def extract_key_persons(photos: list[PhotoForClustering]) -> list[str]:
    """提取分组内出现频次最高的 person_ids（取 top-3）。"""
    person_count: dict[str, int] = {}
    for p in photos:
        for pid in p.person_ids:
            person_count[pid] = person_count.get(pid, 0) + 1
    sorted_persons = sorted(person_count.items(), key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in sorted_persons[:3]]
```

**主角人物分布检查**：

```python
def check_hero_person_distribution(
    groups: list[ChapterGroup],
    hero_person_id: str | None,
) -> list[ChapterGroup]:
    """检查主角人物在章节中的分布。

    若主角只集中在一个章节，降低该章节的置信度。
    这确保 hero_person_id 约束在聚类层就被考虑（规范 6.4/13）。
    """
    if not hero_person_id:
        return groups

    chapters_with_hero = 0
    for group in groups:
        has_hero = any(
            hero_person_id in p.person_ids
            for p in group.photos
            if hasattr(p, 'person_ids')
        )
        if has_hero:
            chapters_with_hero += 1

    # 主角只出现在 <=1 个章节 → 标记低置信度
    if chapters_with_hero <= 1 and len(groups) > 1:
        for group in groups:
            group.degrade_reasons.append("hero_person_concentrated")

    return groups
```

### 4.5 章节标题增强

```python
def generate_chapter_title(
    group: ChapterGroup,
    scene_mode: SceneMode,
    chapter_index: int,
) -> str:
    # 优先级1：有 scene_tags → 用场景标签命名
    scene_tags = extract_scene_tags(group.photos)
    if scene_tags:
        tag = scene_tags[0]
        # 场景标签中英文映射（可扩展）
        tag_names = {
            "beach": "海边", "snow": "雪地", "birthday": "生日",
            "sunset": "日落", "dinner": "聚餐", "ceremony": "典礼",
        }
        name = tag_names.get(tag, tag)
        return f"{name}时光"

    # 优先级2~4：复用 Phase 1 逻辑
    # ...
```

### 4.6 Phase 2 交付标准

- [ ] 有 `scene_tags` 时，标题使用场景标签命名
- [ ] 有 `person_ids` 时，`ChapterPlanItem.key_person_ids` 填充正确
- [ ] 主角人物分布不均时，`degrade_reasons` 包含 `"hero_person_concentrated"`
- [ ] 场景/人物信号缺失时，降级到纯时间分组，`degrade_reasons` 记录原因
- [ ] 全量测试通过

---

## 5. Phase 3：完整功能与生产就绪

> 目标：缓存、可重放、局部重排支持、边界情况全覆盖。

### 5.1 可重放性（规范 2.3）

**缓存键组成**：

```python
def build_clustering_cache_key(
    album_id: str,
    photo_ids: list[str],
    scene_mode: SceneMode,
    pipeline_version: str,
) -> str:
    """聚类结果缓存键（规范 8.1）。

    组成: album_id + photo_set_hash + scene_mode + pipeline_version
    """
    payload = {
        "album_id": album_id,
        "photo_ids": sorted(photo_ids),
        "scene_mode": scene_mode.value,
        "pipeline_version": pipeline_version,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return f"clustering:{hashlib.sha256(encoded).hexdigest()[:16]}"
```

**失效触发器**（规范 8.2）：

| 触发事件 | 失效范围 |
|---------|---------|
| 照片替换或删除 | 该 album_id 的聚类缓存 |
| `pipeline_version` 变更（如阈值调整） | 全部聚类缓存 |
| `hero_person_id` 变更 | 该 album_id 的聚类缓存 |

### 5.2 局部重排支持（规范 6.4）

用户微调操作对聚类层的影响范围：

| 操作 | 影响范围 | 说明 |
|------|---------|------|
| `merge_chapters` | 合并涉及的章节 | 两个章节合并为一个，重算 title/confidence |
| `split_chapter` | 被拆分的章节 | 按时间中点拆分为两个章节 |
| `reorder_chapters` | 全部章节 | 仅调整 order 字段，不重新聚类 |
| `set_hero_person` | 全部章节 | 需重新评估主角分布，可能触发重聚类 |
| `replace_photo` | 当前章节 | 若新照片时间跨章节边界，可能触发相邻章节重算 |

**局部重排实现原则**：

```python
def recluster_for_operation(
    current_plan: ChapterPlan,
    operation_type: str,
    affected_chapter_ids: list[str],
    photos: list[PhotoForClustering],
    scene_mode: SceneMode,
) -> ChapterPlan:
    """局部重排：只重算受影响的章节，保留未受影响的章节不变。

    规范 6.4：局部修改优先，改章节结构允许触发页面规划及其下游重算。
    """
    if operation_type in ("merge_chapters", "split_chapter", "reorder_chapters"):
        # 章节结构变化 → 允许触发页面规划重算
        # 但不需要重新执行照片清洗
        pass

    if operation_type == "set_hero_person":
        # 全局偏好 → 需要重新评估全部章节
        # 规范 13：set_hero_person 不得只改评分权重
        pass
    # ...
```

### 5.3 空输入与异常处理（规范 9.3）

> 注：空输入和单张照片的处理已在 Phase 1 的 `cluster_chapters` 主函数中实现（见 3.5.2），
> 此处不再重复。Phase 3 重点关注更多边界情况。

```python
def cluster_chapters(photos, scene_mode, hero_person_id=None):
    # 已在 Phase 1 实现：
    # - 空输入 → 返回空列表 []
    # - 单张照片 → 单章节，degrade_reasons=["single_photo"]
    # Phase 3 补充：
    # - 全部 rank_weight <= 0 → 返回空列表（已覆盖）
    # - 所有照片 captured_at 完全相同 → 单章节，degrade_reasons=["no_time_gap"]
    pass
```

### 5.4 Phase 3 交付标准

- [ ] 聚类结果可缓存，缓存键包含 `pipeline_version`
- [ ] `merge_chapters` / `split_chapter` / `reorder_chapters` 操作只重算受影响章节
- [ ] `set_hero_person` 触发全量重评估
- [ ] 空输入返回空列表，不抛异常
- [ ] 单张照片返回单章节，`degrade_reasons` 包含 `"single_photo"`
- [ ] `pipeline_version` 变更时旧缓存失效
- [ ] 全量测试通过，含局部重排范围验证用例

---

## 6. 契约变更清单

### 6.1 各 Phase 契约变更汇总

| Phase | 文件 | 变更类型 | 变更内容 | 影响范围 |
|-------|------|---------|---------|---------|
| 1 | `workflow_contracts.py` | 修改 | `ChapterPlanItem` 加 `degrade_reasons: list[str]` | 向后兼容 |
| 1 | `algorithms/__init__.py` | 新增 | 算法包 | 新增 |
| 1 | `algorithms/chapter_clustering.py` | 新增 | 聚类算法模块 | 新增 |
| 1 | `graph/chapter_clustering_node.py` | 修改 | 替换占位逻辑 | 本节点 |
| 1 | `tests/conftest.py` | 修改 | 补充有时间数据的 fixture | 测试 |
| 2 | `algorithms/chapter_clustering.py` | 修改 | 融合聚类策略 | 本模块 |

### 6.2 对 `BookLayout.version` 的影响

- Phase 1/2/3 的聚类逻辑变更**不影响 `BookLayout.version` 的计算方式**（由 `finalize_node` 基于 `base_version` 决定）
- 但聚类结果变化会导致 `input_hash` 变化（因为 `photo_ids` 的分组方式变了），从而使旧缓存失效
- 这符合规范 8.2："用户微调生成新布局版本时必须使相关缓存失效"

### 6.3 对缓存键的影响

| 缓存类型 | 当前键 | Phase 3 新增键 |
|---------|--------|--------------|
| 聚类结果 | 无 | `clustering:{album_id}:{photo_set_hash}:{scene_mode}:{pipeline_version}` |
| 布局结果 | `album_id + photo_set_hash + style + ...` | 不变（聚类结果通过 `input_hash` 间接影响） |

---

## 7. 测试计划

### 7.1 Phase 1 测试

#### 算法单元测试（`tests/algorithms/test_chapter_clustering.py`）

| 编号 | 用例 | 输入 | 预期 |
|------|------|------|------|
| U1 | 时间均匀分布 → 按 gap 切分 | 5张照片，间隔1d/1d/8d/1d，annual 模式 | 2个章节 |
| U2 | 小章节自动合并 | 3组（5张/1张/4张） | 合并1张的组，共2个章节 |
| U3 | 完全无时间 → 单章兜底 | 5张照片，captured_at 全 None | 1个章节，`degrade_reasons=["no_time_data"]` |
| U4 | 代表图选择 | 3张照，权重 0.8/0.5/0.3 | 选 0.8 的那张 |
| U5 | annual vs event 阈值差异 | 相同时间分布（间隔3天），不同 scene_mode | annual: 1章，event: 2章 |
| U6 | 部分无时间混入 | 3张有时间/2张无时间 | 有时间的分组，无时间的追加到最后一个分组 |
| U7 | 标题生成-annual | annual 模式，5月时间范围 | "2026年·五月时光" |
| U8 | 标题生成-event | event 模式，第2章 | "精彩瞬间·二" |
| U9 | 空输入 | 0张照片 | 空列表 `[]` |
| U10 | 单张照片 | 1张照片 | 1个章节，`degrade_reasons=["single_photo"]` |
| U11 | 置信度计算-正常 | 时间均匀、3~50张、无降级 | confidence > 0.7 |
| U12 | 置信度计算-降级 | 有降级标记 | confidence < 0.7 |
| U13 | 第一个章节太小 | 第1组2张/第2组5张 | 合并到第2组，共1个章节 |

#### 节点集成测试（`tests/graph/test_chapter_clustering_node.py`）

| 编号 | 用例 | 预期 |
|------|------|------|
| I1 | 当前 fixture（3张无时间）→ 单章兜底 | `chapter_count=1`，包含全部 p1/p2/p3，`degrade_reasons=["no_time_data"]` |
| I2 | 有时间数据的多章 | `chapter_count > 1`，每章有正确的 `photo_ids` 和 `time_range` |
| I3 | 空输入（0张有效照） | `chapter_count=0`，不抛异常 |
| I4 | 全部 deprioritize 但 rank_weight > 0 | 仍有输出，`cover_photo_id` 选 rank_weight 最高的 |
| I5 | 50张照片（压力测试） | `3 <= chapter_count <= 20`，每章至少有 3 张（合并后） |

### 7.2 Phase 2 测试（增量）

| 编号 | 用例 | 预期 |
|------|------|------|
| U14 | 有 scene_tags 时标题使用场景标签 | 输入 `scene_tags=["beach"]` → 标题含"海边" |
| U15 | key_person_ids 提取 | 3张照片含 person_001/person_002 → `key_person_ids` 正确 |
| U16 | hero_person 集中在一个章节 | `degrade_reasons` 包含 `"hero_person_concentrated"` |
| U17 | 场景标签缺失 → 降级到时间分组 | `degrade_reasons` 记录降级原因 |

### 7.3 Phase 3 测试（增量）

| 编号 | 用例 | 对应规范 |
|------|------|---------|
| U18 | 缓存键包含 pipeline_version | 规范 8.1 |
| U19 | pipeline_version 变更 → 缓存失效 | 规范 8.2 |
| U20 | merge_chapters 局部重排 | 规范 6.4/11.2 |
| U21 | split_chapter 局部重排 | 规范 6.4/11.2 |
| U22 | reorder_chapters 只改 order | 规范 6.4 |
| U23 | set_hero_person 触发全量重评估 | 规范 13 |

### 7.4 规范必测覆盖

| 必测类型 | 覆盖用例 | Phase |
|---------|---------|-------|
| 成功主流程 | I2 | 1 |
| 版本冲突 | （由服务层测试覆盖） | - |
| 非法状态迁移 | I3（空输入不崩溃） | 1 |
| 局部重排范围验证 | U20/U21/U22 | 3 |
| 降级结果不可下单 | I1 + `degrade_reasons` 标记 | 1 |

---

## 8. 与上下游的协作协议

### 8.1 与人员 A（后端平台）的协议

| 事项 | 负责方 | 约定 |
|------|--------|------|
| `KeptPhoto.captured_at` 的数据填充 | A（照片清洗层/特征提取层） | 字段已存在（默认 `None`），A 需在照片清洗层填充真实 EXIF 时间 |
| `KeptPhoto.person_ids` / `scene_tags` / `location_cluster` 的数据填充 | A（特征提取层） | 字段已存在（默认空），Phase 2 需要，A 需在特征提取任务中调用 CLIP/FaceNet 并回填 |
| `ChapterPlanItem.degrade_reasons` 对 `finalize_node` 的影响 | B 通知 A | 新字段通过 `model_dump()` 自动序列化到 `BookLayout.chapters`，A 需确认前端能容忍 |
| 聚类缓存存储位置 | A（Redis/PG） | B 提供缓存键计算函数，A 负责缓存读写和失效 |
| `degrade_reasons` 对 `TaskState.degrade_reasons` 的传递 | A（服务层） | B 在 `ChapterPlanItem.degrade_reasons` 标记，A 在服务层决定是否传播到 `TaskState` |

### 8.2 与人员 C（前端）的协议

| 事项 | 说明 |
|------|------|
| `ChapterPlanItem` 新增字段 | 纯新增，不影响现有解析。前端可选用 `cover_photo_id` 展示章节封面、`time_range` 展示时间标签 |
| `degrade_reasons` 非空时 | 前端可展示温和提示（如"部分照片未能自动分类，已按时间排列"），不展示技术错误 |
| `cluster_confidence < 0.5` 时 | 前端可标记该章节为"建议调整"，引导用户在 HITL #1 中确认 |

### 8.3 与其他 B 层（第3/4/5层算法）的协议

| 上下游 | 协议 |
|--------|------|
| 第3层（页面规划） | 消费 `ChapterPlan.chapters`，每个 `ChapterPlanItem` 的 `photo_ids` 是该章节的候选照片池 |
| 第5层（全书评分） | 可消费 `cluster_confidence` 和 `degrade_reasons` 辅助评分：低置信度章节扣分 |
| 第5层（回退） | `retry_chapter_clustering` 时，本节点重新执行，输入不变则输出不变（可重放） |

#### 8.3.1 下游节点消费代码示例

**第3层（页面规划）节点中读取 `ChapterPlan`：**

```python
def pagination_planning_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    chapter_plan = state.chapter_plan  # 本节点产出

    for chapter in chapter_plan.chapters:
        # chapter.photo_ids              — 该章节候选照片池（已去重、已排序）
        # chapter.cover_photo_id         — 代表图，可用于章节扉页
        # chapter.cluster_confidence     — 聚类置信度（None 或 < 0.5 建议降低该章节页数预算）
        # chapter.degrade_reasons        — 非空说明聚类质量差（如 "no_time_data"），可选择保守策略
        # chapter.time_range             — 时间范围，辅助生成章节时间标签
        # chapter.order                  — 章节序号，保证页码顺序
        pass
```

**第5层（全书评分）节点中读取 `ChapterPlan`：**

```python
def book_scoring_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    chapter_plan = state.chapter_plan

    for chapter in chapter_plan.chapters:
        # 低置信度章节 → 扣分，计入 repair_hints
        if chapter.cluster_confidence is not None and chapter.cluster_confidence < 0.5:
            state.score_snapshot.repair_hints.append(
                RepairHint(
                    chapter_id=chapter.chapter_id,
                    level="retry_chapter_clustering",
                    reason=f"聚类置信度过低 ({chapter.cluster_confidence})",
                )
            )

        # 降级原因影响评分
        if "no_time_data" in chapter.degrade_reasons:
            # 无法验证时间连续性，降低节奏分
            state.score_snapshot.scores["rhythm_score"] -= 0.1
```

---

## 附录 A：文件结构总览

```
backend/src/pixelpress_backend/
├── algorithms/                          ← Phase 1 新建
│   ├── __init__.py
│   └── chapter_clustering.py            ← 聚类算法（纯函数）
├── graph/
│   └── chapter_clustering_node.py       ← 修改：替换占位逻辑
├── models/
│   └── workflow_contracts.py            ← 修改：ChapterPlanItem 加 degrade_reasons
└── ...

backend/tests/
├── algorithms/                          ← Phase 1 新建
│   └── test_chapter_clustering.py       ← 算法单元测试
├── graph/
│   └── test_chapter_clustering_node.py  ← 修改：扩充集成测试
└── conftest.py                          ← 修改：补充有时间数据的 fixture
```

## 附录 B：开发顺序 Checklist

### Phase 0（无需改代码）
- [ ] `uv sync` 安装依赖
- [ ] `uv run pytest -v` 全量测试通过
- [ ] API 端到端调用成功

### Phase 1
- [ ] 修改 `workflow_contracts.py`：`ChapterPlanItem` 加 `degrade_reasons` 字段
- [ ] 新建 `algorithms/__init__.py`
- [ ] 新建 `algorithms/chapter_clustering.py`：实现 `cluster_chapters` 及辅助函数
- [ ] 修改 `graph/chapter_clustering_node.py`：替换占位逻辑
- [ ] 修改 `tests/conftest.py`：补充有时间数据的 fixture
- [ ] 新建 `tests/algorithms/test_chapter_clustering.py`：13 个单元测试
- [ ] 修改 `tests/graph/test_chapter_clustering_node.py`：5 个集成测试
- [ ] `uv run pytest -v` 全量测试通过
- [ ] API 端到端验证

### Phase 2
- [ ] 修改 `algorithms/chapter_clustering.py`：融合聚类策略、主角分布检查、标题增强（`KeptPhoto`/`ChapterPlanItem` 字段已存在，无需改契约）
- [ ] 补充测试
- [ ] `uv run pytest -v` 全量测试通过

### Phase 3
- [ ] 实现缓存键计算和失效逻辑
- [ ] 实现局部重排（merge/split/reorder/set_hero_person）
- [ ] 补充测试（含局部重排范围验证）
- [ ] `uv run pytest -v` 全量测试通过

---

## 附录 C：LLM 增强规划

> 版本：v0.1 | 状态：draft
> 本附录记录节点二后续接入大模型的可行优化点、规范约束和实现路径。
> 所有 LLM 增强均为远期规划，不影响 Phase 1~3 的确定性实现。

### C.1 核心原则

1. **LLM 产出必须是结构化的、可缓存的、通过适配器消费的**——不在聚类节点内直接调用 LLM 服务
2. **节点二的职责是消费结构化信号做确定性聚类**——LLM 推理应发生在上游（特征提取）或下游（文案润色），而非聚类决策环节
3. **降级兜底必须完整**——LLM 不可用时自动回退到当前规则逻辑，且降级状态必须在契约中显式标记
4. **先补契约，再加适配器，最后改节点逻辑**——任何 LLM 增强都必须先更新 `ChapterClusteringInput`/`ChapterClusteringOutput` 契约

### C.2 可行优化点

#### C.2.1 章节标题生成（优先级 P0）

**现状**：`generate_chapter_title` 为纯规则式，输出格式固定（"2026年·五月时光" / "精彩瞬间·一" / "第N章"）。

**LLM 增强**：传入照片的 `scene_tags` + `person_ids` + `time_range` + 前后章节上下文，生成更有叙事感的标题。

**实现路径**：

1. 新增 `LLMTitleAdapter`（独立适配器，不在节点内）
2. `ChapterPlanItem` 契约加 `title_source: Literal["rule", "llm"] = "rule"`，标记标题来源
3. `metadata` 加 `title_model_version: str | None`，满足可重放要求
4. 节点通过适配器异步消费 LLM 结果，超时/失败时 `title_source` 回退为 `"rule"`

**契约变更**：

```python
class ChapterPlanItem(BaseSchema):
    # ... 已有字段 ...
    title_source: Literal["rule", "llm"] = "rule"  # 标题来源标记
```

**降级策略**：

| 场景 | 行为 |
|------|------|
| LLM 调用成功 | `title_candidate` 使用 LLM 输出，`title_source = "llm"` |
| LLM 超时/失败 | `title_candidate` 使用规则输出，`title_source = "rule"` |
| 部分章节 LLM 成功、部分失败 | 混合状态，每章独立标记 `title_source` |

#### C.2.2 叙事摘要（优先级 P2）

**现状**：`ClusteringSummary` 仅有 `chapter_count`、`avg_photos_per_chapter`、`low_confidence_chapters` 三个统计量，无语义化描述。

**LLM 增强**：为每个章节生成 1~2 句叙事摘要，供前端 HITL 审核界面使用。

**实现路径**：

1. `ChapterPlanItem` 契约加 `narrative_summary: str | None = None`
2. 由独立 Worker 生成，节点从缓存读取
3. `metadata` 加 `summary_model_version: str | None`

**契约变更**：

```python
class ChapterPlanItem(BaseSchema):
    # ... 已有字段 ...
    narrative_summary: str | None = None  # 叙事摘要（LLM 生成，可为 None）
```

**前端消费**：HITL 审核页直接展示 `narrative_summary`，`None` 时不展示。

#### C.2.3 语义断裂检测（优先级 P4）

**现状**：`_fusion_split` 按 `scene_tags` / `person_ids` / `location_cluster` 的标签突变拆分，无法判断语义连续性（如"海滩日落 → 海边晚餐"标签不同但叙事连续）。

**LLM 增强**：对相邻候选边界注入 LLM 判断叙事连续性。

**实现路径**：

1. **不应替换 `_fusion_split`**——语义判断应作为上游特征提取的结构化输出
2. 新增 `KeptPhoto.semantic_boundary_score: float | None = None`，由特征提取 Worker 预计算
3. 节点消费该字段作为拆分依据，与 `scene_tags` 等信号并列

**契约变更**：

```python
class KeptPhoto(BaseSchema):
    # ... 已有字段 ...
    semantic_boundary_score: float | None = None  # 与下一张照片的语义断裂分值（0=连续, 1=断裂）
```

**优势**：节点逻辑保持确定性，LLM 推理前移到特征提取阶段，结果可缓存、可重放。

#### C.2.4 置信度语义化（优先级 P1，但归属评分层）

**现状**：`compute_cluster_confidence` 为纯数学公式（`0.4 * uniformity + 0.3 * count_score + 0.3 * no_degrade`），无法判断语义一致性。

**LLM 增强**：让 LLM 评估分组的语义一致性，输出置信度和理由。

**归属判断**：这是**评分层（节点五）的增强**，而非聚类层的职责。聚类层只产出结构化信号和规则置信度，语义评估应由评分层消费 `ChapterPlan` 后独立完成。

**实现路径**：在 `book_scoring_node` 中新增 LLM 评分维度，不在 `chapter_clustering_node` 中修改。

### C.3 不建议用 LLM 的点

#### C.3.1 封面图选择

**原因**：`KeptPhoto` 已有 `saliency_score`（显著性）、`face_integrity_score`（人脸完整性）、`rank_weight`（综合权重）三个结构化字段。用这些字段做加权评分比 LLM 判断更确定性、更可重放、更快。

**建议**：在 `select_cover_photo` 中扩展为多字段加权：

```python
def select_cover_photo(photos: list[PhotoForClustering]) -> str | None:
    """选择代表图：多字段加权评分。"""
    def cover_score(p: PhotoForClustering) -> float:
        return (
            0.4 * p.rank_weight
            + 0.3 * (p.saliency_score or 0.0)
            + 0.3 * (p.face_integrity_score or 0.0)
        )
    candidates = sorted(
        [p for p in photos if p.rank_weight > 0],
        key=cover_score, reverse=True,
    )
    return candidates[0].photo_id if candidates else None
```

#### C.3.2 degrade_reasons 翻译

**原因**：技术标签（如 `"no_time_data"`）翻译为用户可读提示是**前端展示层的职责**，不应在节点内做。节点只产出技术标签，翻译映射表放前端 i18n 配置。

**前端映射表示例**：

| 技术标签 | 用户提示 |
|---------|---------|
| `no_time_data` | 部分照片缺少拍摄时间，已按默认顺序排列 |
| `partial_time_data` | 部分照片时间信息不完整，分类可能不准确 |
| `merged_small_chapter` | 照片较少的时段已合并到相邻章节 |
| `hero_person_concentrated` | 主角人物集中在少数章节，建议检查分布 |

### C.4 规范约束清单

接入 LLM 时必须满足以下规范条款：

| 规范条款 | 约束 | 应对 |
|---------|------|------|
| 2.1 先契约后实现 | LLM 相关字段必须先写入契约定义 | 先更新 `ChapterClusteringInput`/`ChapterClusteringOutput`，再编码 |
| 2.3 可重放 | LLM 输出不确定，破坏 `seed + pipeline_version + input_hash` 重放保证 | `metadata` 中记录 `title_model_version` / `summary_model_version`，纳入 input_hash 计算；LLM 结果缓存后复用 |
| 5.1 节点不跨层消费 | LLM 推理结果是模型服务层产出，聚类节点直接消费等于跨层 | 通过适配器（`LLMTitleAdapter`）或上游特征提取的结构化字段间接消费 |
| 5.2 副作用隔离 | LLM 调用是外部服务调用，不得混进算法节点 | LLM 调用放在独立 Worker / 适配器，节点只读缓存或结构化字段 |
| 9.1 降级不等于成功 | LLM 部分失败时必须显式标记 | `title_source` / `narrative_summary` 等字段标记来源，混合状态逐章标记 |
| 10.1 主架构优先级 | 一期主架构为 `FastAPI + LangGraph`，LLM 推理由 Python 异步 Worker 承载 | 不在 LangGraph 节点内同步调用 LLM，通过异步队列 + 缓存消费 |

### C.5 实现路径总结

```
Step 1: 补契约
  - ChapterPlanItem 加 title_source / narrative_summary
  - KeptPhoto 加 semantic_boundary_score（如需语义断裂检测）
  - 更新 ChapterClusteringInput / ChapterClusteringOutput

Step 2: 加适配器层
  - 新建 adapters/llm_title_adapter.py
  - 新建 adapters/llm_summary_adapter.py
  - 定义超时、重试、降级策略

Step 3: 改节点逻辑
  - chapter_clustering_node 通过适配器消费 LLM 结果
  - 降级时回退到规则逻辑
  - metadata 记录 model_version

Step 4: 补测试
  - LLM 成功路径
  - LLM 超时/失败降级路径
  - 混合状态（部分成功部分降级）
  - 可重放验证（相同 input + model_version → 相同 output）
```
