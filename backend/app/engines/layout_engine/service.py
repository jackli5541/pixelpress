from __future__ import annotations

from html import escape
from typing import Any

from app.engines.layout_engine.freeform import build_freeform_layout, description_height


PAGE_SIZES_MM: dict[str, tuple[float, float]] = {
    "A4": (210, 297),
    "A5": (148, 210),
    "square_10inch": (200, 200),
}


LAYOUT_TEMPLATES: dict[str, dict[str, Any]] = {
    "full_page": {
        "name": "Full Page",
        "slots": 1,
        "css_class": "layout-full",
        "description": "Single hero image with generous breathing room.",
    },
    "cinema_landscape": {
        "name": "Cinema Landscape",
        "slots": 1,
        "css_class": "layout-cinema-landscape",
        "description": "Single wide image with a cinematic horizon emphasis.",
    },
    "gallery_portrait": {
        "name": "Gallery Portrait",
        "slots": 1,
        "css_class": "layout-gallery-portrait",
        "description": "Single upright image framed like a gallery print.",
    },
    "half_half": {
        "name": "Half Half",
        "slots": 2,
        "css_class": "layout-half-half",
        "description": "Two stacked frames for paired moments.",
    },
    "two_column": {
        "name": "Two Column",
        "slots": 2,
        "css_class": "layout-two-col",
        "description": "Balanced left-right comparison layout.",
    },
    "staggered_duo": {
        "name": "Staggered Duo",
        "slots": 2,
        "css_class": "layout-staggered-duo",
        "description": "Two photos with an offset rhythm for story beats.",
    },
    "grid_3": {
        "name": "Grid Three",
        "slots": 3,
        "css_class": "layout-grid-3",
        "description": "One wide anchor photo with two supporting frames.",
    },
    "grid_4": {
        "name": "Grid Four",
        "slots": 4,
        "css_class": "layout-grid-4",
        "description": "Tight four-photo contact sheet arrangement.",
    },
    "one_large_two_small": {
        "name": "One Large Two Small",
        "slots": 3,
        "css_class": "layout-1big-2small",
        "description": "A dominant hero frame supported by two detail shots.",
    },
    "triptych_strip": {
        "name": "Triptych Strip",
        "slots": 3,
        "css_class": "layout-triptych-strip",
        "description": "Three evenly weighted images for a linear sequence.",
    },
    "mosaic_mix": {
        "name": "Mosaic Mix",
        "slots": 4,
        "css_class": "layout-mosaic-mix",
        "description": "One anchor tile with three supporting snapshots.",
    },
}

SLOT_TO_TEMPLATE: dict[int, str] = {
    1: "full_page",
    2: "half_half",
    3: "one_large_two_small",
    4: "grid_4",
}


def _photo_orientation(photo: dict[str, Any]) -> str:
    width = photo.get("width")
    height = photo.get("height")
    if not width or not height:
        return "unknown"
    if width > height * 1.12:
        return "landscape"
    if height > width * 1.12:
        return "portrait"
    return "square"


def _select_template_key(photos: list[dict[str, Any]]) -> str:
    count = min(max(len(photos), 1), 4)
    orientations = [_photo_orientation(photo) for photo in photos]
    portrait_count = orientations.count("portrait")
    landscape_count = orientations.count("landscape")

    if count == 1:
        if landscape_count == 1:
            return "cinema_landscape"
        if portrait_count == 1:
            return "gallery_portrait"
        return "full_page"
    if count == 2:
        if portrait_count == 2:
            return "half_half"
        if landscape_count >= 1:
            return "two_column"
        return "staggered_duo"
    if count == 3:
        if portrait_count >= 2:
            return "one_large_two_small"
        if landscape_count >= 2:
            return "triptych_strip"
        return "grid_3"
    if portrait_count >= 3:
        return "mosaic_mix"
    return "grid_4"


CSS_STYLES = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { background: #d9d1c4; }
body {
  font-family: 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
  color: #111827;
  padding: 16px 0 28px;
}
.page {
  width: var(--page-width, 210mm);
  height: var(--page-height, 297mm);
  margin: 0 auto 18px;
  position: relative;
  page-break-after: always;
  break-after: page;
}
.page:last-child { page-break-after: auto; break-after: auto; }
.print-page-shell {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  padding: var(--page-safe-margin, 8mm);
  background:
    radial-gradient(circle at top right, rgba(255,255,255,0.5), transparent 35%),
    linear-gradient(180deg, rgba(255,255,255,0.16), transparent 32%),
    var(--page-bg, #fff);
  color: var(--page-primary, #111827);
}
.print-page-shell::before {
  content: "";
  position: absolute;
  inset: calc(var(--page-safe-margin, 8mm) / 2.2);
  border: 1px solid var(--page-border, rgba(17,24,39,0.12));
  pointer-events: none;
}
.print-page-shell::after {
  content: "";
  position: absolute;
  right: -8%;
  top: -10%;
  width: 42%;
  height: 34%;
  background: var(--page-ornament, linear-gradient(135deg, rgba(192,132,87,0.22), rgba(17,24,39,0.08)));
  filter: blur(10px);
  opacity: 0.8;
  border-radius: 999px;
  pointer-events: none;
}
.page-inner {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 5mm;
}
.page-copy {
  width: min(72%, 124mm);
  display: flex;
  flex-direction: column;
  gap: 2mm;
}
.page-copy.align-center {
  width: 100%;
  align-items: center;
  text-align: center;
}
.page-kicker,
.page-role {
  font-family: var(--page-body-font, 'Noto Sans SC', sans-serif);
  text-transform: uppercase;
  letter-spacing: 0.22em;
  color: var(--page-accent, #c08457);
  font-size: 8pt;
}
.page-copy h3 {
  font-family: var(--page-display-font, var(--page-heading-font, 'Georgia', serif));
  color: var(--page-primary, #111827);
  font-size: 23pt;
  line-height: 1.05;
  letter-spacing: 0.01em;
}
.page-subtitle,
.page-summary {
  font-family: var(--page-body-font, 'Noto Sans SC', sans-serif);
  color: var(--page-secondary, #6b7280);
  font-size: 10pt;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}
.page-media {
  flex: 1;
  min-height: 0;
  display: flex;
}
.freeform-layout {
  position: relative;
  width: 100%;
  height: 100%;
}
.freeform-photo {
  position: absolute;
  margin: 0;
  padding: 0;
  overflow: visible;
  background: transparent;
  box-shadow: none;
}
.freeform-photo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.page-description {
  position: absolute;
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--page-secondary, #6b7280);
  font: 9pt/1.55 var(--page-body-font, 'Noto Sans SC', sans-serif);
  background: transparent;
}
.photo-layout {
  width: 100%;
  height: 100%;
}
.slot {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 1.8mm;
  padding: 2.2mm;
  border-radius: 4mm;
  background: var(--page-panel-bg, rgba(255,255,255,0.72));
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}
.slot-media {
  position: relative;
  flex: 1;
  min-height: 0;
  border-radius: 2.4mm;
  overflow: hidden;
  background: rgba(255,255,255,0.6);
}
.slot img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.photo-caption {
  font-size: 8.3pt;
  line-height: 1.45;
  color: var(--page-secondary, #6b7280);
  font-family: var(--page-body-font, 'Noto Sans SC', sans-serif);
  background: var(--page-caption-bg, rgba(255,255,255,0.88));
  border-radius: 2.2mm;
  padding: 1.3mm 1.6mm;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}
.page-number {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  bottom: calc(var(--page-safe-margin, 8mm) + 1mm);
  min-width: 10mm;
  text-align: center;
  padding: 1mm 2.4mm;
  border-radius: 999px;
  background: transparent;
  border: 0;
  color: var(--page-secondary, #6b7280);
  font-size: 8.2pt;
}

.layout-full { display: block; }
.layout-full .slot { height: 100%; }

.layout-cinema-landscape {
  display: grid;
  grid-template-rows: 1fr;
}
.layout-cinema-landscape .slot {
  height: 100%;
  padding: 3.2mm;
}
.layout-cinema-landscape .slot-media {
  min-height: 0;
}
.layout-cinema-landscape img {
  object-fit: cover;
}

.layout-gallery-portrait {
  display: flex;
  justify-content: center;
  align-items: stretch;
}
.layout-gallery-portrait .slot {
  width: min(76%, 110mm);
  margin: 0 auto;
}

.layout-half-half {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 4mm;
}

.layout-two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4mm;
}

.layout-staggered-duo {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  gap: 4mm;
  align-items: end;
}
.layout-staggered-duo .slot:last-child {
  transform: translateY(10mm);
}

.layout-grid-4 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 4mm;
}

.layout-grid-3 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1.18fr 1fr;
  gap: 4mm;
}
.layout-grid-3 .slot:first-child { grid-column: 1 / -1; }

.layout-1big-2small {
  display: grid;
  grid-template-columns: 1.45fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 4mm;
}
.layout-1big-2small .slot:first-child { grid-row: 1 / -1; }

.layout-triptych-strip {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 4mm;
}

.layout-mosaic-mix {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  grid-template-rows: 1fr 1fr 1fr;
  gap: 4mm;
}
.layout-mosaic-mix .slot:first-child {
  grid-row: 1 / span 2;
}
.layout-mosaic-mix .slot:nth-child(4) {
  grid-column: 1 / -1;
}

.role-opening .page-inner { gap: 6mm; }
.role-opening .page-copy h3 { font-size: 28pt; }
.role-opening .page-media { padding-top: 1mm; }

.role-closing .page-copy {
  width: min(62%, 110mm);
  margin-left: auto;
  text-align: right;
}
.role-closing .page-copy.align-center { margin-left: 0; }

.role-hero_spread .print-page-shell {
  padding: calc(var(--page-safe-margin, 8mm) * 0.7);
}
.role-hero_spread .page-copy {
  width: min(56%, 100mm);
  background: var(--page-panel-bg, rgba(255,255,255,0.72));
  padding: 4mm;
  border-radius: 4mm;
  backdrop-filter: blur(3px);
}
.role-hero_spread .page-media .slot {
  padding: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
.role-hero_spread .page-media .slot-media {
  border-radius: 0;
}
.role-hero_spread .photo-caption {
  position: absolute;
  left: 4mm;
  bottom: 4mm;
  max-width: 52%;
}

.cover-page,
.chapter-divider,
.album-closer {
  padding: 0;
}
.cover-page::before,
.cover-page::after,
.chapter-divider::before,
.chapter-divider::after,
.album-closer::before,
.album-closer::after {
  display: none;
}
.cover-page {
  background: var(--page-cover-gradient, linear-gradient(145deg, #f7f1e8 0%, #fffdf8 52%, #efe5d6 100%));
}
.chapter-divider {
  background: var(--page-chapter-gradient, linear-gradient(145deg, #fbf7f1 0%, #fffdf8 100%));
}
.album-closer {
  background: linear-gradient(180deg, rgba(255,255,255,0.7), rgba(255,255,255,0.25)), var(--page-bg, #fff);
}
.hero-band {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(255,255,255,0) 20%, rgba(17,24,39,0.08) 100%),
    var(--page-ornament, linear-gradient(135deg, rgba(192,132,87,0.22), rgba(17,24,39,0.08)));
  mix-blend-mode: multiply;
}
.cover-content,
.chapter-content,
.closer-content {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  padding: calc(var(--page-safe-margin, 8mm) * 1.45);
  gap: 4mm;
}
.cover-content.align-center,
.chapter-content.align-center,
.closer-content.align-center {
  align-items: center;
  text-align: center;
}
.cover-title,
.chapter-title,
.closer-title {
  font-family: var(--page-display-font, var(--page-heading-font, 'Georgia', serif));
  color: var(--page-primary, #111827);
  line-height: 0.98;
}
.cover-title { font-size: 34pt; max-width: 120mm; }
.chapter-title { font-size: 28pt; max-width: 120mm; }
.closer-title { font-size: 25pt; max-width: 110mm; }
.cover-subtitle,
.chapter-desc,
.closer-text {
  font-family: var(--page-body-font, 'Noto Sans SC', sans-serif);
  font-size: 11pt;
  line-height: 1.6;
  color: var(--page-secondary, #6b7280);
  max-width: 110mm;
}
.cover-meta,
.chapter-meta,
.closer-meta {
  display: flex;
  gap: 3mm;
  flex-wrap: wrap;
}
.meta-pill {
  padding: 1.3mm 2.2mm;
  border-radius: 999px;
  border: 1px solid var(--page-border, rgba(17,24,39,0.12));
  background: rgba(255,255,255,0.45);
  color: var(--page-primary, #111827);
  font-size: 8.2pt;
}

@media print {
  html, body { background: #fff; padding: 0; }
  .page { margin: 0; }
}
"""


def select_template(
    photos: list[dict[str, Any]],
    page_size: str = "A4",
) -> dict[str, Any]:
    count = min(max(len(photos), 1), 4)
    template_key = _select_template_key(photos) if photos else SLOT_TO_TEMPLATE.get(count, "grid_4")
    template = LAYOUT_TEMPLATES.get(template_key, LAYOUT_TEMPLATES["grid_4"])
    return {
        "template": template_key,
        "template_name": template["name"],
        "slots": template["slots"],
        "css_class": template["css_class"],
        "photo_count": count,
        "page_size": page_size,
    }


def plan_pages(
    photos: list[dict[str, Any]],
    page_size: str = "A4",
    photos_per_page: int = 3,
) -> list[dict[str, Any]]:
    if not photos:
        return []

    clamped_per_page = min(max(photos_per_page, 1), 4)
    pages: list[dict[str, Any]] = []
    for index in range(0, len(photos), clamped_per_page):
        page_photos = photos[index:index + clamped_per_page]
        template = select_template(page_photos, page_size)
        pages.append(
            {
                "page_number": len(pages) + 1,
                "photo_ids": [item["id"] for item in page_photos],
                "photo_count": len(page_photos),
                "template": template,
            }
        )
    return pages


def _dimensions_for(print_spec: dict[str, Any] | None) -> tuple[float, float]:
    book_size = (print_spec or {}).get("book_size", "A4")
    return PAGE_SIZES_MM.get(book_size, PAGE_SIZES_MM["A4"])


def _resolve_style(style_key: str, style_presets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    base_style = {
        "heading_font": "'Georgia', serif",
        "body_font": "'Noto Sans SC', sans-serif",
        "display_font": "'Georgia', serif",
        "primary_color": "#111827",
        "secondary_color": "#6b7280",
        "accent_color": "#c08457",
        "background": "#ffffff",
        "panel_background": "rgba(255,255,255,0.78)",
        "border_color": "rgba(17,24,39,0.12)",
        "caption_background": "rgba(255,255,255,0.88)",
        "ornament_gradient": "linear-gradient(135deg, rgba(192,132,87,0.22), rgba(17,24,39,0.08))",
        "cover_gradient": "linear-gradient(145deg, #f7f1e8 0%, #fffdf8 52%, #efe5d6 100%)",
        "chapter_gradient": "linear-gradient(145deg, #fbf7f1 0%, #fffdf8 100%)",
        "copy_alignment": "left",
    }
    return base_style | style_presets.get(style_key, {})


def _style_vars(style: dict[str, Any], print_spec: dict[str, Any] | None) -> str:
    width_mm, height_mm = _dimensions_for(print_spec)
    safe_margin = float((print_spec or {}).get("safe_margin_mm", 8))
    return ";".join(
        [
            f"--page-width:{width_mm}mm",
            f"--page-height:{height_mm}mm",
            f"--page-bg:{style['background']}",
            f"--page-primary:{style['primary_color']}",
            f"--page-secondary:{style['secondary_color']}",
            f"--page-accent:{style['accent_color']}",
            f"--page-heading-font:{style['heading_font']}",
            f"--page-body-font:{style['body_font']}",
            f"--page-display-font:{style.get('display_font', style['heading_font'])}",
            f"--page-panel-bg:{style.get('panel_background', 'rgba(255,255,255,0.78)')}",
            f"--page-border:{style.get('border_color', 'rgba(17,24,39,0.12)')}",
            f"--page-caption-bg:{style.get('caption_background', 'rgba(255,255,255,0.88)')}",
            f"--page-ornament:{style.get('ornament_gradient', 'linear-gradient(135deg, rgba(192,132,87,0.22), rgba(17,24,39,0.08))')}",
            f"--page-cover-gradient:{style.get('cover_gradient', style['background'])}",
            f"--page-chapter-gradient:{style.get('chapter_gradient', style['background'])}",
            f"--page-safe-margin:{safe_margin}mm",
        ]
    )


def _copy_alignment_class(style: dict[str, Any]) -> str:
    return "align-center" if style.get("copy_alignment") == "center" else ""


def _page_role_label(page_role: str) -> str:
    mapping = {
        "opening": "Chapter Opening",
        "standard": "Story Page",
        "closing": "Chapter Closing",
        "hero_spread": "Hero Spread",
    }
    return mapping.get(page_role, "Story Page")


def _render_copy_block(title: str, subtitle: str, page_role: str, style: dict[str, Any]) -> str:
    title_html = f"<h3>{escape(title)}</h3>" if title else ""
    subtitle_html = f'<p class="page-subtitle">{escape(subtitle)}</p>' if subtitle else ""
    if not (title_html or subtitle_html):
        return ""
    return (
        f'<header class="page-copy {_copy_alignment_class(style)}">'
        f'<p class="page-role">{escape(_page_role_label(page_role))}</p>'
        f"{title_html}"
        f"{subtitle_html}"
        "</header>"
    )


def _caption_for(photo: dict[str, Any], captions_map: dict[str, str]) -> str:
    photo_id = str(photo.get("id", ""))
    caption = captions_map.get(photo_id, "").strip()
    if caption:
        return caption
    fallback = str(photo.get("custom_caption", "") or "").strip()
    return fallback[:120]


def _render_slots(photos: list[dict[str, Any]], captions_map: dict[str, str]) -> str:
    parts: list[str] = []
    for index, photo in enumerate(photos):
        src = str(photo.get("src") or photo.get("url") or "")
        filename = escape(str(photo.get("filename") or f"photo-{index + 1}"))
        caption = _caption_for(photo, captions_map)
        caption_html = f'<figcaption class="photo-caption">{escape(caption)}</figcaption>' if caption else ""
        parts.append(
            "<figure class=\"slot\">"
            f'<div class="slot-media"><img src="{escape(src, quote=True)}" alt="{filename}" loading="eager" /></div>'
            f"{caption_html}"
            "</figure>"
        )
    return "".join(parts)


def _render_freeform(layout_meta: dict[str, Any], photos: list[dict[str, Any]]) -> str:
    photos_by_id = {str(photo.get("id")): photo for photo in photos}
    parts: list[str] = []
    for element in sorted(layout_meta.get("elements", []), key=lambda item: int(item.get("order", 0))):
        photo = photos_by_id.get(str(element.get("photo_id")))
        if not photo:
            continue
        src = escape(str(photo.get("src") or photo.get("url") or ""), quote=True)
        alt = escape(str(photo.get("filename") or "photo"), quote=True)
        style = ";".join(
            f"{key}:{float(element[value]) * 100:.6f}%"
            for key, value in (("left", "x"), ("top", "y"), ("width", "width"), ("height", "height"))
        )
        parts.append(f'<figure class="freeform-photo" data-photo-id="{escape(str(element.get("photo_id")), quote=True)}" style="{style}"><img src="{src}" alt="{alt}" loading="eager" /></figure>')
    description = layout_meta.get("description") or {}
    text = str(description.get("text") or "").strip()
    if text:
        width = float(description.get("width", 0.64))
        height = description_height(text, width)
        style = ";".join((
            f"left:{float(description.get('x', 0.18)) * 100:.6f}%",
            f"top:{float(description.get('y', 0.72)) * 100:.6f}%",
            f"width:{width * 100:.6f}%",
            f"min-height:{height * 100:.6f}%",
        ))
        parts.append(f'<p class="page-description" style="{style}">{escape(text)}</p>')
    return "".join(parts)


def generate_layout_html(
    layout: dict[str, Any],
    photos: list[dict[str, Any]],
    page_number: int = 1,
    page_meta: dict[str, Any] | None = None,
    style_presets: dict[str, dict[str, Any]] | None = None,
    print_spec: dict[str, Any] | None = None,
) -> str:
    page_meta = page_meta or {}
    style_presets = style_presets or {}
    style_key = str(page_meta.get("style_key") or "minimal")
    style = _resolve_style(style_key, style_presets)
    page_role = str(page_meta.get("page_role") or "standard")
    title = str(page_meta.get("title") or "").strip()[:80]
    subtitle = str(page_meta.get("subtitle") or "").strip()[:120]
    captions_map = {
        str(item.get("photo_id")): str(item.get("text") or "")[:120]
        for item in page_meta.get("captions", [])
        if isinstance(item, dict) and item.get("photo_id")
    }
    width_mm, height_mm = _dimensions_for(print_spec)
    safe_margin = float((print_spec or {}).get("safe_margin_mm", 8))
    layout_meta = build_freeform_layout(
        photos,
        page_meta,
        page_width_mm=width_mm,
        page_height_mm=height_mm,
        safe_margin_mm=safe_margin,
    )
    freeform_html = _render_freeform(layout_meta, photos)
    css_class = layout.get("css_class", "layout-grid-3")
    shell_classes = f"print-page-shell role-{escape(page_role)} count-{len(photos)} template-{escape(str(layout.get('template', 'grid_3')))}"
    return (
        f'<div class="page" style="{_style_vars(style, print_spec)}">'
        f'<section class="{shell_classes}">'
        '<div class="page-inner">'
        f'<div class="page-media"><div class="freeform-layout">{freeform_html}</div></div>'
        "</div>"
        f'<div class="page-number">{page_number}</div>'
        "</section>"
        "</div>"
    )


def generate_cover_html(
    album_name: str,
    cover_title: str | None,
    *,
    style_key: str,
    style_presets: dict[str, dict[str, Any]] | None = None,
    print_spec: dict[str, Any] | None = None,
    chapter_count: int = 0,
    photo_count: int = 0,
) -> str:
    style = _resolve_style(style_key, style_presets or {})
    alignment = _copy_alignment_class(style)
    title = escape((cover_title or album_name or "Album").strip())
    subtitle = escape(album_name.strip()) if cover_title and cover_title.strip() and cover_title.strip() != album_name.strip() else ""
    subtitle_html = f'<p class="cover-subtitle">{subtitle}</p>' if subtitle else ""
    return (
        f'<div class="page" style="{_style_vars(style, print_spec)}">'
        '<section class="print-page-shell cover-page">'
        '<div class="hero-band"></div>'
        f'<div class="cover-content {alignment}">'
        '<p class="page-kicker">Print Album</p>'
        f'<h1 class="cover-title">{title}</h1>'
        f"{subtitle_html}"
        '<div class="cover-meta">'
        f'<span class="meta-pill">{photo_count} Photos</span>'
        f'<span class="meta-pill">{chapter_count} Chapters</span>'
        f'<span class="meta-pill">{escape(style.get("label", style_key))}</span>'
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def generate_chapter_divider_html(
    chapter_name: str,
    chapter_description: str,
    *,
    chapter_index: int,
    photo_count: int,
    page_count: int,
    style_key: str,
    style_presets: dict[str, dict[str, Any]] | None = None,
    print_spec: dict[str, Any] | None = None,
) -> str:
    style = _resolve_style(style_key, style_presets or {})
    alignment = _copy_alignment_class(style)
    return (
        f'<div class="page" style="{_style_vars(style, print_spec)}">'
        '<section class="print-page-shell chapter-divider">'
        f'<div class="chapter-content {alignment}">'
        f'<p class="page-kicker">Chapter {chapter_index:02d}</p>'
        f'<h2 class="chapter-title">{escape(chapter_name)}</h2>'
        f'<p class="chapter-desc">{escape((chapter_description or "").strip()[:180])}</p>'
        '<div class="chapter-meta">'
        f'<span class="meta-pill">{photo_count} Photos</span>'
        f'<span class="meta-pill">{page_count} Pages</span>'
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def generate_album_closer_html(
    album_name: str,
    *,
    style_key: str,
    style_presets: dict[str, dict[str, Any]] | None = None,
    print_spec: dict[str, Any] | None = None,
    photo_count: int = 0,
    chapter_count: int = 0,
    page_count: int = 0,
) -> str:
    style = _resolve_style(style_key, style_presets or {})
    alignment = _copy_alignment_class(style)
    return (
        f'<div class="page" style="{_style_vars(style, print_spec)}">'
        '<section class="print-page-shell album-closer">'
        f'<div class="closer-content {alignment}">'
        '<p class="page-kicker">Album Complete</p>'
        f'<h2 class="closer-title">{escape(album_name)}</h2>'
        '<p class="closer-text">A print-ready sequence with structured chapters, controlled styling, and export-safe imagery.</p>'
        '<div class="closer-meta">'
        f'<span class="meta-pill">{photo_count} Photos</span>'
        f'<span class="meta-pill">{chapter_count} Chapters</span>'
        f'<span class="meta-pill">{page_count} Story Pages</span>'
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def generate_full_html(
    pages_plan: list[dict[str, Any]],
    photos_by_id: dict[str, dict[str, Any]],
    album_name: str = "Album",
) -> str:
    pages_html = ""
    for page in pages_plan:
        page_photos = [photos_by_id[pid] for pid in page["photo_ids"] if pid in photos_by_id]
        if not page_photos:
            continue
        pages_html += generate_layout_html(page["template"], page_photos, page["page_number"]) + "\n"

    return (
        "<!DOCTYPE html>"
        '<html lang="zh-CN"><head><meta charset="utf-8" />'
        f"<title>{escape(album_name)}</title><style>{CSS_STYLES}</style></head><body>{pages_html}</body></html>"
    )


def adjust_layout(
    current_layout: dict[str, Any],
    instruction: str,
) -> dict[str, Any]:
    instruction_lower = instruction.lower()
    if "full" in instruction_lower or "全页" in instruction:
        current_layout["template"] = "full_page"
    elif "half" in instruction_lower or "对半" in instruction:
        current_layout["template"] = "half_half"
    elif "two" in instruction_lower or "双栏" in instruction:
        current_layout["template"] = "two_column"
    elif "grid_3" in instruction_lower or "三图" in instruction:
        current_layout["template"] = "grid_3"
    elif "grid_4" in instruction_lower or "四图" in instruction:
        current_layout["template"] = "grid_4"
    elif "1big" in instruction_lower or "一大两小" in instruction:
        current_layout["template"] = "one_large_two_small"

    template = LAYOUT_TEMPLATES.get(current_layout["template"], LAYOUT_TEMPLATES["grid_4"])
    current_layout["template_name"] = template["name"]
    current_layout["css_class"] = template["css_class"]
    current_layout["slots"] = template["slots"]
    return current_layout
