"""版式模板定义、元数据与兼容性评分。

- 模板来源于 layout-dsl.md（扩展至 12 种）
- TemplateMetadata 包含标识、匹配约束、槽位定义、适用场景四类字段
- Compatibility Score 使用 8 因子加权评分，argmax 选最优模板
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


# === 枚举定义 ===


class CropMode(str, Enum):
    AUTO_BEST = "auto_best"
    FACE_CENTER = "face_center"
    SUBJECT_CENTER = "subject_center"
    CENTER = "center"
    FIT = "fit"


class PageType(str, Enum):
    SINGLE = "single"
    SPREAD = "spread"


class Orientation(str, Enum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"
    ANY = "any"


class DecorationMode(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    MODERATE = "moderate"
    RICH = "rich"


# === 数据类 ===


@dataclass
class SlotDefinition:
    """模板槽位定义。"""
    id: str
    geometry_fraction: tuple[float, float, float, float]  # (x%, y%, w%, h%)
    crop: CropMode = CropMode.AUTO_BEST
    bleed: bool = True
    priority: int = 0          # 填充优先级，hero_slot 的 priority > 0
    optional: bool = False
    constraints: dict = field(default_factory=dict)


@dataclass
class TextBlockDef:
    """模板文本块定义。"""
    id: str
    type: Literal["title", "subtitle", "body", "page_number", "caption"]
    position: str
    style: dict = field(default_factory=dict)


@dataclass
class TemplateMetadata:
    """生产级模板元数据。

    字段分为四类：标识、匹配约束、槽位定义、适用场景。
    """
    # === 标识字段 ===
    template_id: str
    layout_family: str
    variant_name: str
    version: str = "1.0.0"
    page_type: str = "single"

    # === 匹配约束 ===
    supported_photo_count: list[int] = field(default_factory=list)
    min_photo_count: int = 1
    max_photo_count: int = 1
    hero_slot_count: int = 0
    supported_orientation: list[str] = field(default_factory=lambda: ["any"])
    preferred_orientation: str = "any"
    min_photo_quality: float = 0.0
    require_face: bool = False
    require_subject: bool = False
    min_resolution_dpi: int = 150

    # === 槽位结构 ===
    slots: list[SlotDefinition] = field(default_factory=list)
    text_blocks: list[TextBlockDef] = field(default_factory=list)

    # === 适用场景 ===
    suitable_page_roles: list[str] = field(default_factory=list)
    suitable_album_types: list[str] = field(default_factory=lambda: ["universal"])
    decoration_mode: str = "none"
    gutter_safe: bool = False

    # === 元信息 ===
    description: str = ""
    tags: list[str] = field(default_factory=list)
    deprecated: bool = False


# === 12 种 MVP 模板注册表 ===

TEMPLATE_REGISTRY: dict[str, TemplateMetadata] = {
    # ── 原有 6 种 ──
    "tpl_single_full_bleed": TemplateMetadata(
        template_id="tpl_single_full_bleed",
        layout_family="single", variant_name="full_bleed",
        page_type="single",
        supported_photo_count=[1], min_photo_count=1, max_photo_count=1,
        hero_slot_count=1, supported_orientation=["any"],
        slots=[SlotDefinition(id="photo_0", geometry_fraction=(3, 3, 94, 94), priority=1)],
        text_blocks=[TextBlockDef(id="pagenum", type="page_number", position="bottom_center")],
        suitable_page_roles=["hero", "collage", "ending", "general"],
        decoration_mode="none", gutter_safe=True,
        description="通用单图满版",
    ),
    "tpl_double_side_by_side": TemplateMetadata(
        template_id="tpl_double_side_by_side",
        layout_family="double", variant_name="side_by_side",
        page_type="single",
        supported_photo_count=[2], min_photo_count=2, max_photo_count=2,
        hero_slot_count=0, supported_orientation=["any"],
        slots=[
            SlotDefinition(id="photo_l", geometry_fraction=(3, 5, 45.5, 90), priority=0),
            SlotDefinition(id="photo_r", geometry_fraction=(51.5, 5, 45.5, 90), priority=0),
        ],
        suitable_page_roles=["collage", "ending", "general"],
        decoration_mode="minimal", gutter_safe=True,
        description="双图左右对开",
    ),
    "tpl_triple_narrative": TemplateMetadata(
        template_id="tpl_triple_narrative",
        layout_family="triple", variant_name="narrative",
        page_type="single",
        supported_photo_count=[3], min_photo_count=3, max_photo_count=3,
        hero_slot_count=1, supported_orientation=["any"],
        slots=[
            SlotDefinition(id="hero", geometry_fraction=(3, 5, 58, 90), priority=1),
            SlotDefinition(id="sub_1", geometry_fraction=(63, 5, 34, 43), priority=0),
            SlotDefinition(id="sub_2", geometry_fraction=(63, 52, 34, 43), priority=0),
        ],
        suitable_page_roles=["hero", "collage"],
        decoration_mode="minimal", gutter_safe=True,
        description="三图叙事，一大两小",
    ),
    "tpl_grid_nine": TemplateMetadata(
        template_id="tpl_grid_nine",
        layout_family="grid", variant_name="3x3",
        page_type="single",
        supported_photo_count=[4, 5, 6, 7, 8, 9], min_photo_count=4, max_photo_count=9,
        hero_slot_count=0, supported_orientation=["any"],
        slots=[
            SlotDefinition(id=f"g_{r}_{c}", geometry_fraction=(3 + 30.3 * c, 4 + 29.3 * r, 28.3, 27.3), priority=0)
            for r in range(3) for c in range(3)
        ],
        suitable_page_roles=["collage"],
        decoration_mode="minimal", gutter_safe=True,
        description="九宫格（支持 4~9 张）",
    ),
    "tpl_chapter_cover": TemplateMetadata(
        template_id="tpl_chapter_cover",
        layout_family="chapter", variant_name="cover",
        page_type="single",
        supported_photo_count=[1], min_photo_count=1, max_photo_count=1,
        hero_slot_count=1, supported_orientation=["any"],
        require_subject=True,
        slots=[SlotDefinition(id="cover", geometry_fraction=(3, 3, 94, 70), priority=1)],
        text_blocks=[TextBlockDef(id="title", type="title", position="center")],
        suitable_page_roles=["chapter_opening"], suitable_album_types=["universal"],
        decoration_mode="rich", gutter_safe=True,
        description="章节扉页",
    ),
    "tpl_spread_full_bleed": TemplateMetadata(
        template_id="tpl_spread_full_bleed",
        layout_family="spread", variant_name="full_bleed",
        page_type="spread",
        supported_photo_count=[1], min_photo_count=1, max_photo_count=1,
        hero_slot_count=1, supported_orientation=["landscape"],
        slots=[SlotDefinition(id="spread", geometry_fraction=(1, 3, 98, 94), priority=1)],
        suitable_page_roles=["hero", "chapter_opening"],
        decoration_mode="none", gutter_safe=False,  # 需 Gutter Safe Validator 校验
        description="跨页满版",
    ),

    # ── 新增 6 种 ──
    "tpl_hero_left": TemplateMetadata(
        template_id="tpl_hero_left",
        layout_family="hero", variant_name="left",
        page_type="single",
        supported_photo_count=[1], min_photo_count=1, max_photo_count=1,
        hero_slot_count=1, supported_orientation=["portrait", "square"],
        slots=[SlotDefinition(id="hero", geometry_fraction=(3, 5, 58, 90), priority=1)],
        text_blocks=[TextBlockDef(id="title", type="title", position="bottom_right")],
        suitable_page_roles=["hero", "chapter_opening"],
        decoration_mode="moderate", gutter_safe=True,
        description="主图左，留白右（可放文字）",
    ),
    "tpl_hero_right": TemplateMetadata(
        template_id="tpl_hero_right",
        layout_family="hero", variant_name="right",
        page_type="single",
        supported_photo_count=[1], min_photo_count=1, max_photo_count=1,
        hero_slot_count=1, supported_orientation=["portrait", "square"],
        slots=[SlotDefinition(id="hero", geometry_fraction=(39, 5, 58, 90), priority=1)],
        text_blocks=[TextBlockDef(id="title", type="title", position="bottom_left")],
        suitable_page_roles=["hero", "chapter_opening"],
        decoration_mode="moderate", gutter_safe=True,
        description="主图右，留白左（可放文字）",
    ),
    "tpl_hero_center": TemplateMetadata(
        template_id="tpl_hero_center",
        layout_family="hero", variant_name="center",
        page_type="single",
        supported_photo_count=[1], min_photo_count=1, max_photo_count=1,
        hero_slot_count=1, supported_orientation=["landscape", "square"],
        slots=[SlotDefinition(id="hero", geometry_fraction=(5, 12, 90, 76), priority=1)],
        text_blocks=[TextBlockDef(id="title", type="title", position="bottom_center")],
        suitable_page_roles=["hero", "chapter_opening"],
        decoration_mode="minimal", gutter_safe=True,
        description="主图居中，上下留白",
    ),
    "tpl_double_compare": TemplateMetadata(
        template_id="tpl_double_compare",
        layout_family="double", variant_name="compare",
        page_type="single",
        supported_photo_count=[2], min_photo_count=2, max_photo_count=2,
        hero_slot_count=1, supported_orientation=["any"],
        slots=[
            SlotDefinition(id="hero", geometry_fraction=(3, 5, 58, 90), priority=1),
            SlotDefinition(id="sub", geometry_fraction=(63, 35, 34, 60), priority=0),
        ],
        suitable_page_roles=["collage", "general"],
        decoration_mode="minimal", gutter_safe=True,
        description="对比式双图，一大一小",
    ),
    "tpl_single_portrait": TemplateMetadata(
        template_id="tpl_single_portrait",
        layout_family="single", variant_name="portrait",
        page_type="single",
        supported_photo_count=[1], min_photo_count=1, max_photo_count=1,
        hero_slot_count=1, supported_orientation=["portrait"],
        slots=[SlotDefinition(id="photo", geometry_fraction=(10, 5, 80, 90), priority=1)],
        suitable_page_roles=["hero", "general"],
        decoration_mode="none", gutter_safe=True,
        description="竖图满版（侧留白）",
    ),
    "tpl_single_landscape": TemplateMetadata(
        template_id="tpl_single_landscape",
        layout_family="single", variant_name="landscape",
        page_type="single",
        supported_photo_count=[1], min_photo_count=1, max_photo_count=1,
        hero_slot_count=1, supported_orientation=["landscape"],
        slots=[SlotDefinition(id="photo", geometry_fraction=(3, 15, 94, 70), priority=1)],
        suitable_page_roles=["hero", "general"],
        decoration_mode="none", gutter_safe=True,
        description="横图满版（上下留白）",
    ),
}


# === 辅助函数 ===


def _classify_orientation(photo) -> str:
    """根据宽高比返回 'landscape' | 'portrait' | 'square'。

    阈值：ratio > 1.3 → landscape, ratio < 0.77 → portrait, 否则 square。
    1/1.3 ≈ 0.77，保证对称性。
    """
    w = getattr(photo, 'width', None)
    h = getattr(photo, 'height', None)
    if not w or not h:
        return "square"
    ratio = w / h
    if ratio > 1.3:
        return "landscape"
    if ratio < 0.77:
        return "portrait"
    return "square"


def _estimate_dpi(photo) -> float:
    """简化 DPI 估算——基于百万像素数。

    假设印刷尺寸为 A4_square (210×210mm ≈ 8.3×8.3inch)，
    粗略判断：≥4MP → 充足, ≥2MP → 可接受, <1MP → 不足。
    大部分现代照片 >4MP，因此默认高分。
    """
    w = getattr(photo, 'width', None)
    h = getattr(photo, 'height', None)
    if not w or not h:
        return 200  # 无数据时假设合格
    mp = (w * h) / 1_000_000
    if mp >= 4:
        return 300
    if mp >= 2:
        return 200
    if mp >= 1:
        return 120
    return 72


# === 各因子评分函数 ===


def _score_photo_count_match(t: TemplateMetadata, photos: list) -> float:
    """图片数量匹配度（权重 0.20）。

    硬约束：< min 或 > max → 0.0（理论上外层已过滤，此处二次校验）。
    精确命中 supported_photo_count → 1.0，范围内未精确命中 → 0.5。
    """
    n = len(photos)
    if n < t.min_photo_count:
        return 0.0
    if t.max_photo_count > 0 and n > t.max_photo_count:
        return 0.0
    if n in t.supported_photo_count:
        return 1.0
    return 0.5


def _score_orientation_match(t: TemplateMetadata, photos: list) -> float:
    """横竖图匹配度（权重 0.25，最高权重）。

    模板支持 "any" → 满分。
    逐张匹配：朝向在 supported_orientation 中 → 1 分，否则 0 分。
    supported_orientation 是硬约束，不匹配无宽容分。
    """
    if "any" in t.supported_orientation:
        return 1.0

    matches = 0.0
    for p in photos:
        o = _classify_orientation(p)
        if o in t.supported_orientation:
            matches += 1.0
        # 不匹配且 template 不支持 "any" → 0 分，不给予部分宽容分
    return matches / max(len(photos), 1)


def _score_hero_fit(t: TemplateMetadata, photos: list) -> float:
    """Hero Photo 适配度（权重 0.20）。

    模板无 hero_slot → 满分（无需求）。
    有 hero_slot → 取候选照片中 hero_score 最高值。
    Phase 1 中 hero_score 默认为 0，所有模板公平扣分。
    """
    if t.hero_slot_count == 0:
        return 1.0
    hero_scores = [getattr(p, 'hero_score', 0.0) for p in photos]
    return max(hero_scores) if hero_scores else 0.0


def _score_page_role_match(t: TemplateMetadata, context: dict) -> float:
    """页面角色适配度（权重 0.15）。

    精确匹配 → 1.0，模板支持 general → 0.5，否则 → 0.2。
    """
    role = context.get("page_role", "general")
    if role in t.suitable_page_roles:
        return 1.0
    if "general" in t.suitable_page_roles:
        return 0.5
    return 0.2


def _score_face_safety(t: TemplateMetadata, photos: list) -> float:
    """人脸安全适配度（权重 0.10）。

    模板不要求人脸 → 满分。
    要求人脸时按比例评分：全有人脸 → 1.0，部分 → 0.5，全无 → 0.1。
    """
    if not t.require_face:
        return 1.0
    faces = sum(1 for p in photos if getattr(p, 'face_boxes', []))
    if faces == len(photos):
        return 1.0
    if faces > 0:
        return 0.5
    return 0.1


def _score_diversity(t: TemplateMetadata, context: dict) -> float:
    """多样性约束（权重 0.05）。

    连续 3 页同一 layout_family → 0.0（强制排除）。
    连续 2 页 → 0.3（降分）。
    否则 → 1.0。
    """
    prev = context.get("prev_template_ids", [])
    if not prev:
        return 1.0
    if len(prev) >= 2 and prev[-1] == t.layout_family and prev[-2] == t.layout_family:
        return 0.0
    if prev[-1] == t.layout_family:
        return 0.3
    return 1.0


def _score_resolution_match(t: TemplateMetadata, photos: list) -> float:
    """分辨率适配度（权重 0.03）。

    逐张判断 DPI 是否 ≥ 模板最低要求，返回达标比例。
    """
    if not photos:
        return 1.0
    ok = sum(1 for p in photos if _estimate_dpi(p) >= t.min_resolution_dpi)
    return ok / len(photos)


def _score_album_type_match(t: TemplateMetadata, context: dict) -> float:
    """相册类型适配度（权重 0.02）。

    弱加成：匹配 → 0.2，不匹配 → 0.0。
    注意：返回值不是 1.0，这是设计意图——弱信号不影响核心选择。
    """
    album_type = context.get("album_type", "universal")
    return 0.2 if album_type in t.suitable_album_types else 0.0


# === 主选择函数 ===


def compute_template_compatibility(
    template: TemplateMetadata,
    photos: list,
    context: dict,
) -> float:
    """计算模板兼容性评分 (0~1)。

    加权算术平均：Σ(w_i × s_i) / Σ(w_i)。

    Args:
        template: 候选模板元数据。
        photos: 候选照片列表（须有 width/height，可选 face_boxes/hero_score）。
        context: 上下文 dict，键包括 page_role, album_type, prev_template_ids, style。

    Returns:
        0.0 ~ 1.0 的兼容性评分。数量硬约束不满足时直接返回 0.0。
    """
    # 数量硬约束
    if len(photos) < template.min_photo_count:
        return 0.0
    if template.max_photo_count > 0 and len(photos) > template.max_photo_count:
        return 0.0

    weights = {
        "count": 0.20,
        "orientation": 0.25,
        "hero": 0.20,
        "role": 0.15,
        "face": 0.10,
        "diversity": 0.05,
        "resolution": 0.03,
        "album": 0.02,
    }

    scores = {
        "count": _score_photo_count_match(template, photos),
        "orientation": _score_orientation_match(template, photos),
        "hero": _score_hero_fit(template, photos),
        "role": _score_page_role_match(template, context),
        "face": _score_face_safety(template, photos),
        "diversity": _score_diversity(template, context),
        "resolution": _score_resolution_match(template, photos),
        "album": _score_album_type_match(template, context),
    }

    total = sum(weights[k] * scores[k] for k in weights) / sum(weights.values())
    return round(total, 4)


def select_best_template(
    templates: list[TemplateMetadata],
    photos: list,
    context: dict,
    min_threshold: float = 0.3,
) -> tuple[TemplateMetadata, float]:
    """从候选模板中 argmax 选出最佳模板。

    对所有候选模板计算 compatibility_score，按分数降序排序取最高分。
    若最高分 < min_threshold（默认 0.3），回退到 tpl_single_full_bleed。

    Args:
        templates: 候选模板列表。
        photos: 候选照片列表。
        context: 上下文 dict。
        min_threshold: 最低接受阈值，低于此值触发兜底。

    Returns:
        (最佳模板, 兼容性评分)。
    """
    if not templates:
        fallback = TEMPLATE_REGISTRY["tpl_single_full_bleed"]
        return fallback, compute_template_compatibility(fallback, photos, context)

    scored = [(t, compute_template_compatibility(t, photos, context)) for t in templates]
    scored.sort(key=lambda x: -x[1])

    if scored[0][1] >= min_threshold:
        return scored[0]

    fallback = TEMPLATE_REGISTRY["tpl_single_full_bleed"]
    return fallback, compute_template_compatibility(fallback, photos, context)
