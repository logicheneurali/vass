"""Document generation tools — HTML to PDF via Playwright Chromium."""
import json
import re
from pathlib import Path


async def html_to_pdf(html: str, filename: str, allowed_root: str) -> str:
    """Generate a PDF from HTML content using Playwright Chromium.

    Args:
        html: Full HTML document content
        filename: Base name without extension (auto-renamed if exists)
        allowed_root: Allowed root directory for output

    Returns:
        JSON string with path and status
    """
    try:
        from .playwright import _get_browser
    except ImportError:
        return json.dumps({"error": "Playwright not available"})

    safe = re.sub(r'[/\\:*?"<>|]', '_', filename.strip())
    if not safe:
        safe = "document"

    root = Path(allowed_root).resolve()
    pdf_path = root / f"{safe}.pdf"
    i = 1
    while pdf_path.exists():
        pdf_path = root / f"{safe}_{i}.pdf"
        i += 1

    html_path = root / f"{safe}_tmp.html"
    try:
        html_path.write_text(html, encoding="utf-8")

        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(
                html_path.as_uri(),
                wait_until="networkidle",
                timeout=30000,
            )
            await page.pdf(path=str(pdf_path), format="A4")
        finally:
            await page.close()

        html_path.unlink(missing_ok=True)

        return json.dumps({
            "path": str(pdf_path),
            "name": pdf_path.name,
            "ok": True,
        }, ensure_ascii=False)

    except Exception as e:
        html_path.unlink(missing_ok=True)
        return json.dumps({"error": str(e)})
