"""PDF 导出引擎 —— 使用 Playwright (Chromium) 将 HTML 转换为 PDF。

依赖: playwright + 已安装的 Chromium 浏览器
  pip install playwright
  playwright install chromium

若 Playwright 不可用，自动降级为 HTML 文件导出。
"""

from pathlib import Path
from typing import Any

from app.storage.file_store import get_uploads_root

EXPORTS_DIR = get_uploads_root() / "_exports"

# A4 尺寸 (mm) → 打印 CSS 规格
PAGE_SIZES: dict[str, dict[str, float]] = {
    "A4": {"width": 210, "height": 297},
    "A5": {"width": 148, "height": 210},
    "square_10inch": {"width": 200, "height": 200},
}


def _get_playwright():
    """延迟导入 Playwright，避免未安装时阻塞整个应用。"""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def _html_to_pdf(html_content: str, output_path: Path, page_size: str = "A4") -> bool:
    """使用 Chromium 无头模式将 HTML 转换为 PDF。

    Returns:
        bool: 成功返回 True，Playwright 不可用时返回 False。
    """
    sync_playwright = _get_playwright()
    if sync_playwright is None:
        return False

    size = PAGE_SIZES.get(page_size, PAGE_SIZES["A4"])
    width_mm = size["width"]
    height_mm = size["height"]

    # 注入打印样式确保正确分页
    html_with_print_css = html_content.replace(
        "</head>",
        f"""<style>
  @page {{ size: {width_mm}mm {height_mm}mm; margin: 3mm; }}
  @media print {{ body {{ -webkit-print-color-adjust: exact; }} }}
</style></head>""",
    )

    try:
        playwright = sync_playwright()
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_with_print_css, wait_until="networkidle")
        page.pdf(
            path=str(output_path),
            format="A4" if page_size == "A4" else None,
            width=f"{width_mm}mm",
            height=f"{height_mm}mm",
            print_background=True,
            margin={"top": "3mm", "bottom": "3mm", "left": "3mm", "right": "3mm"},
        )
        browser.close()
        playwright.stop()
        return True
    except Exception:
        return False


def export_to_pdf(
    html_content: str,
    album_name: str,
    export_id: str,
    page_size: str = "A4",
) -> dict[str, Any]:
    """将渲染好的 HTML 导出为 PDF 文件。

    Args:
        html_content: 完整 HTML 文档。
        album_name: 相册名称（用于文件名）。
        export_id: 导出记录 ID。
        page_size: 页面尺寸。

    Returns:
        dict: { "format": "pdf"|"html", "file_path": str, "file_size": int }
    """
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = album_name.replace(" ", "_")[:40]

    # 尝试 PDF 导出
    pdf_path = EXPORTS_DIR / f"{safe_name}_{export_id[:8]}.pdf"
    success = _html_to_pdf(html_content, pdf_path, page_size)

    if success:
        return {
            "format": "pdf",
            "file_path": str(pdf_path),
            "file_size": pdf_path.stat().st_size,
        }

    # 降级：保存 HTML
    html_path = EXPORTS_DIR / f"{safe_name}_{export_id[:8]}.html"
    html_path.write_text(html_content, encoding="utf-8")

    return {
        "format": "html",
        "file_path": str(html_path),
        "file_size": html_path.stat().st_size,
    }
