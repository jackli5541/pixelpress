"""AI 排版引擎 —— 基础逻辑版（不依赖 AI）。

提供：
- 页面规划：将照片分配到各页（每页 1-4 张）
- 模板选择：根据每页照片数量自动选择最优版式
- HTML 渲染：生成美观的 HTML 排版预览
- 排版调整：按用户指令重新生成
"""

from math import ceil
from typing import Any

# ── 版式模板库 ──────────────────────────────────────────────

LAYOUT_TEMPLATES: dict[str, dict[str, Any]] = {
    "full_page": {
        "name": "全页",
        "slots": 1,
        "css_class": "layout-full",
        "description": "单张照片撑满页面",
    },
    "half_half": {
        "name": "上下对半",
        "slots": 2,
        "css_class": "layout-half-half",
        "description": "上下均分两栏",
    },
    "two_column": {
        "name": "双栏",
        "slots": 2,
        "css_class": "layout-two-col",
        "description": "左右对称双栏",
    },
    "grid_3": {
        "name": "三图网格",
        "slots": 3,
        "css_class": "layout-grid-3",
        "description": "上一下二网格",
    },
    "grid_4": {
        "name": "四图网格",
        "slots": 4,
        "css_class": "layout-grid-4",
        "description": "2×2 四宫格",
    },
    "one_large_two_small": {
        "name": "一大两小",
        "slots": 3,
        "css_class": "layout-1big-2small",
        "description": "左侧大图 + 右侧两小图",
    },
}

SLOT_TO_TEMPLATE: dict[int, str] = {
    1: "full_page",
    2: "half_half",
    3: "one_large_two_small",
    4: "grid_4",
}


def select_template(
    photos: list[dict[str, Any]],
    page_size: str = "A4",
) -> dict[str, Any]:
    """根据当前页照片数量自动选择最佳版式模板。

    Args:
        photos: 当前页照片列表。
        page_size: 页面尺寸（A4 / A5 / square）。

    Returns:
        dict: 含 template 名、slots 数、照片分配方式。
    """
    count = len(photos)
    if count > 4:
        count = 4  # 单页最多 4 张
    template_key = SLOT_TO_TEMPLATE.get(count, "grid_4")
    template = LAYOUT_TEMPLATES.get(template_key, LAYOUT_TEMPLATES["grid_4"])

    return {
        "template": template_key,
        "template_name": template["name"],
        "slots": template["slots"],
        "css_class": template["css_class"],
        "photo_count": count,
    }


def plan_pages(
    photos: list[dict[str, Any]],
    page_size: str = "A4",
    photos_per_page: int = 3,
) -> list[dict[str, Any]]:
    """将照片列表拆分为页面规划。

    Args:
        photos: 照片列表。
        page_size: 页面尺寸。
        photos_per_page: 每页目标照片数（1-4）。

    Returns:
        list[dict]: 每页的规划信息（含模板选择、照片分配）。
    """
    if not photos:
        return []

    pages = []
    for i in range(0, len(photos), photos_per_page):
        page_photos = photos[i:i + photos_per_page]
        template = select_template(page_photos, page_size)
        pages.append({
            "page_number": len(pages) + 1,
            "photo_ids": [p["id"] for p in page_photos],
            "photo_count": len(page_photos),
            "template": template,
        })

    return pages


# ── HTML 渲染 ───────────────────────────────────────────────

CSS_STYLES = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'PingFang SC', 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
  background: #fff;
}
.page {
  width: 210mm; height: 297mm;       /* A4 */
  margin: 0 auto; padding: 12mm;
  position: relative; overflow: hidden;
  background: #fefefe;
  page-break-after: always;
}
.page:last-child { page-break-after: auto; }
.page-number {
  position: absolute; bottom: 8mm; right: 12mm;
  font-size: 9pt; color: #999;
}

/* ── 版式 ── */
.layout-full img { width: 100%; height: calc(100% - 4mm); object-fit: contain; }

.layout-half-half { display: flex; flex-direction: column; gap: 4mm; height: 100%; }
.layout-half-half .slot { flex: 1; overflow: hidden; }
.layout-half-half img { width: 100%; height: 100%; object-fit: cover; }

.layout-two-col { display: flex; gap: 4mm; height: 100%; }
.layout-two-col .slot { flex: 1; overflow: hidden; }
.layout-two-col img { width: 100%; height: 100%; object-fit: cover; }

.layout-grid-4 { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 4mm; height: 100%; }
.layout-grid-4 .slot { overflow: hidden; }
.layout-grid-4 img { width: 100%; height: 100%; object-fit: cover; }

.layout-grid-3 { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 4mm; height: 100%; }
.layout-grid-3 .slot:first-child { grid-column: 1 / -1; }
.layout-grid-3 .slot { overflow: hidden; }
.layout-grid-3 img { width: 100%; height: 100%; object-fit: cover; }

.layout-1big-2small { display: grid; grid-template-columns: 3fr 2fr; grid-template-rows: 1fr 1fr; gap: 4mm; height: 100%; }
.layout-1big-2small .slot:first-child { grid-row: 1 / -1; }
.layout-1big-2small .slot { overflow: hidden; }
.layout-1big-2small img { width: 100%; height: 100%; object-fit: cover; }
"""


def generate_layout_html(
    layout: dict[str, Any],
    photos: list[dict[str, Any]],
    page_number: int = 1,
) -> str:
    """将排版方案渲染为单页 HTML。

    Args:
        layout: select_template 的返回结果。
        photos: 当前页照片列表（已排序）。
        page_number: 页码。

    Returns:
        str: 单页 HTML 片段字符串。
    """
    css_class = layout.get("css_class", "layout-grid-3")

    slots_html = ""
    for i, photo in enumerate(photos):
        url = photo.get("url", "")
        filename = photo.get("filename", f"photo-{i}")
        slots_html += f'<div class="slot"><img src="{url}" alt="{filename}" loading="lazy" /></div>\n'

    return f"""<div class="page">
  <div class="{css_class}">
    {slots_html.strip()}
  </div>
  <div class="page-number">{page_number}</div>
</div>"""


def generate_full_html(
    pages_plan: list[dict[str, Any]],
    photos_by_id: dict[str, dict[str, Any]],
    album_name: str = "相册",
) -> str:
    """生成完整相册 HTML（所有页面）。

    Args:
        pages_plan: plan_pages 的返回结果。
        photos_by_id: photo_id → photo 的查找字典。
        album_name: 相册名称。

    Returns:
        str: 完整 HTML 文档。
    """
    pages_html = ""
    for page in pages_plan:
        page_photos = [photos_by_id[pid] for pid in page["photo_ids"] if pid in photos_by_id]
        if not page_photos:
            continue
        pages_html += generate_layout_html(
            page["template"],
            page_photos,
            page["page_number"],
        ) + "\n"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>{album_name}</title>
<style>{CSS_STYLES}</style>
</head>
<body>
{pages_html}
</body>
</html>"""


def adjust_layout(
    current_layout: dict[str, Any],
    instruction: str,
) -> dict[str, Any]:
    """根据用户自然语言指令调整版式（当前为简单规则匹配）。

    后续可接入 Claude API 做语义理解。
    """
    instruction_lower = instruction.lower()

    # 简单指令匹配
    if "全页" in instruction or "full" in instruction_lower:
        current_layout["template"] = "full_page"
    elif "对半" in instruction or "half" in instruction_lower:
        current_layout["template"] = "half_half"
    elif "双栏" in instruction or "two" in instruction_lower:
        current_layout["template"] = "two_column"
    elif "三图" in instruction or "grid_3" in instruction_lower:
        current_layout["template"] = "grid_3"
    elif "四图" in instruction or "grid_4" in instruction_lower:
        current_layout["template"] = "grid_4"
    elif "一大两小" in instruction or "1big" in instruction_lower:
        current_layout["template"] = "one_large_two_small"

    template = LAYOUT_TEMPLATES.get(current_layout["template"], LAYOUT_TEMPLATES["grid_4"])
    current_layout["template_name"] = template["name"]
    current_layout["css_class"] = template["css_class"]
    current_layout["slots"] = template["slots"]

    return current_layout
