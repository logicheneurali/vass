import json

from playwright.async_api import async_playwright

_browser = None
_playwright = None


async def _get_browser():
    global _browser, _playwright
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
    return _browser


async def search_web(query: str, max_results: int = 10) -> str:
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        await page.goto(f"https://html.duckduckgo.com/html/?q={query}", timeout=30000)
        results = []
        items = await page.query_selector_all(".result")
        for item in items[:max_results]:
            title_el = await item.query_selector(".result__title")
            link_el = await item.query_selector(".result__url")
            snippet_el = await item.query_selector(".result__snippet")
            title = (await title_el.inner_text()).strip() if title_el else ""
            link = (await link_el.get_attribute("href")).strip() if link_el else ""
            snippet = (await snippet_el.inner_text()).strip() if snippet_el else ""
            if title and link:
                results.append({"title": title, "url": link, "snippet": snippet})
        return json.dumps(results, ensure_ascii=False, indent=2)
    finally:
        await page.close()


async def fetch_page(url: str, timeout: float = 30.0) -> str:
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines[:250])
    finally:
        await page.close()
