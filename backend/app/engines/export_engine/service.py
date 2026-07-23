from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from app.storage.file_store import get_uploads_root

EXPORTS_DIR = get_uploads_root() / "_exports"

PAGE_SIZES: dict[str, dict[str, float]] = {
    "A4": {"width": 210, "height": 297},
    "A5": {"width": 148, "height": 210},
    "square_10inch": {"width": 254, "height": 254},
}

INVALID_WINDOWS_FILENAME_CHARS = '<>:"/\\|?*'


class PdfExportError(Exception):
    pass


MISSING_CHROMIUM_HINT = (
    "Chromium executable is missing in the current runtime. "
    "Install it with `python -m playwright install chromium` in the backend build/start environment."
)

_browser_lock = asyncio.Lock()
_shared_playwright: Any | None = None
_shared_browser: Any | None = None
_shared_loop: asyncio.AbstractEventLoop | None = None


def _get_playwright():
    try:
        from playwright.async_api import async_playwright

        return async_playwright
    except ImportError:
        return None


async def get_shared_browser():
    global _shared_browser, _shared_loop, _shared_playwright
    current_loop = asyncio.get_running_loop()
    if _shared_loop is current_loop and _shared_browser is not None and _shared_browser.is_connected():
        return _shared_browser
    async with _browser_lock:
        if _shared_loop is current_loop and _shared_browser is not None and _shared_browser.is_connected():
            return _shared_browser
        factory = _get_playwright()
        if factory is None:
            return None
        _shared_playwright = await factory().start()
        _shared_browser = await _shared_playwright.chromium.launch(headless=True)
        _shared_loop = current_loop
        return _shared_browser


async def close_shared_browser() -> None:
    global _shared_browser, _shared_loop, _shared_playwright
    if _shared_browser is not None:
        await _shared_browser.close()
        _shared_browser = None
    if _shared_playwright is not None:
        await _shared_playwright.stop()
        _shared_playwright = None
    _shared_loop = None


def _safe_export_name(album_name: str) -> str:
    cleaned = "".join("_" if char in INVALID_WINDOWS_FILENAME_CHARS else char for char in album_name.strip())
    cleaned = cleaned.replace(" ", "_").strip("._")
    return cleaned[:40] or "album"


def normalize_print_spec(print_spec: dict[str, Any] | None, page_size: str = "A4") -> tuple[dict[str, Any], list[str]]:
    incoming = dict(print_spec or {})
    warnings: list[str] = []

    book_size = str(incoming.get("book_size") or page_size)
    if book_size not in PAGE_SIZES:
        warnings.append(f"unsupported book_size '{book_size}', fallback to {page_size}")
        book_size = page_size if page_size in PAGE_SIZES else "A4"

    try:
        bleed_mm = float(incoming.get("bleed_mm", 3))
    except (TypeError, ValueError):
        bleed_mm = 3.0
        warnings.append("invalid bleed_mm, fallback to 3")
    bleed_mm = min(max(bleed_mm, 0.0), 8.0)

    try:
        safe_margin_mm = float(incoming.get("safe_margin_mm", 8))
    except (TypeError, ValueError):
        safe_margin_mm = 8.0
        warnings.append("invalid safe_margin_mm, fallback to 8")
    safe_margin_mm = min(max(safe_margin_mm, 4.0), 18.0)

    try:
        page_dpi = int(incoming.get("page_dpi", 300))
    except (TypeError, ValueError):
        page_dpi = 300
        warnings.append("invalid page_dpi, fallback to 300")
    page_dpi = min(max(page_dpi, 150), 600)

    color_profile = str(incoming.get("color_profile") or "srgb").lower()
    if color_profile == "rgb":
        color_profile = "srgb"
    if color_profile == "cmyk":
        warnings.append("CMYK conversion is not available in V2; output uses sRGB")
        color_profile = "srgb"
    elif color_profile != "srgb":
        warnings.append(f"unsupported color_profile '{color_profile}', fallback to rgb")
        color_profile = "srgb"

    normalized = {
        "book_size": book_size,
        "bleed_mm": bleed_mm,
        "safe_margin_mm": safe_margin_mm,
        "page_dpi": page_dpi,
        "allow_spread": bool(incoming.get("allow_spread", True)),
        "color_profile": color_profile,
    }
    return normalized, warnings


async def _html_to_pdf(
    html_content: str,
    output_path: Path,
    page_size: str = "A4",
    print_spec: dict[str, Any] | None = None,
) -> tuple[bool, str | None, dict[str, int | bool]]:
    metrics: dict[str, int | bool] = {}
    if _get_playwright() is None:
        return False, "Playwright is not installed", metrics

    normalized_print_spec, _ = normalize_print_spec(print_spec, page_size)
    page_size = normalized_print_spec["book_size"]
    size = PAGE_SIZES.get(page_size, PAGE_SIZES["A4"])
    width_mm = size["width"]
    height_mm = size["height"]
    bleed_mm = float(normalized_print_spec["bleed_mm"])
    sheet_width_mm = width_mm + bleed_mm * 2
    sheet_height_mm = height_mm + bleed_mm * 2

    html_with_print_css = html_content.replace(
        "</head>",
        (
            "<style>"
            f"@page {{ size: {sheet_width_mm}mm {sheet_height_mm}mm; margin: 0; }}"
            "@media print { body { -webkit-print-color-adjust: exact; color-adjust: exact; } }"
            "</style></head>"
        ),
    )

    temp_html_path: Path | None = None
    context = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".html",
            delete=False,
            dir=output_path.parent,
        ) as temp_file:
            temp_file.write(html_with_print_css)
            temp_html_path = Path(temp_file.name)

        browser_reused = _shared_loop is asyncio.get_running_loop() and _shared_browser is not None and _shared_browser.is_connected()
        phase_started = perf_counter()
        browser = await get_shared_browser()
        metrics["browser_acquire_ms"] = round((perf_counter() - phase_started) * 1000)
        metrics["browser_reused"] = browser_reused
        if browser is None:
            return False, "Playwright is not installed", metrics
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(300000)
        phase_started = perf_counter()
        await page.goto(temp_html_path.as_uri(), wait_until="load")
        await page.wait_for_function(
            """
            () => Array.from(document.images).every((img) => img.complete)
            """
        )
        metrics["page_load_ms"] = round((perf_counter() - phase_started) * 1000)
        phase_started = perf_counter()
        await page.pdf(
            path=str(output_path),
            format="A4" if page_size == "A4" else None,
            width=f"{sheet_width_mm}mm",
            height=f"{sheet_height_mm}mm",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        metrics["pdf_write_ms"] = round((perf_counter() - phase_started) * 1000)
        return True, None, metrics
    except Exception as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "Please run the following command to download new browsers" in message:
            return False, f"{message} {MISSING_CHROMIUM_HINT}", metrics
        return False, message, metrics
    finally:
        if context is not None:
            await context.close()
        if temp_html_path is not None and temp_html_path.exists():
            temp_html_path.unlink(missing_ok=True)


async def export_to_pdf(
    html_content: str,
    album_name: str,
    export_id: str,
    page_size: str = "A4",
    print_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_export_name(album_name)
    normalized_print_spec, warnings = normalize_print_spec(print_spec, page_size)

    pdf_path = EXPORTS_DIR / f"{safe_name}_{export_id[:8]}.pdf"
    success, error_message, metrics = await _html_to_pdf(html_content, pdf_path, page_size, print_spec=normalized_print_spec)

    if not success:
        failure_message = "Playwright PDF export failed"
        if error_message:
            failure_message = f"{failure_message}: {error_message[:240]}"
        raise PdfExportError(failure_message)

    return {
        "format": "pdf",
        "file_path": str(pdf_path),
        "file_size": pdf_path.stat().st_size,
        "print_spec": normalized_print_spec,
        "warnings": warnings,
        "metrics": metrics,
    }
