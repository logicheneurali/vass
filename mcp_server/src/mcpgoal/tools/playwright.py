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
    import httpx
    from bs4 import BeautifulSoup
    try:
        if isinstance(max_results, str):
            max_results = int(max_results) if max_results.strip() else 10
    except ValueError:
        max_results = 10
    url = f"https://lite.duckduckgo.com/lite/?q={query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        rows = soup.select("table tr")
        for i, row in enumerate(rows):
            link_el = row.select_one("a.result-link")
            if not link_el:
                continue
            title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            if "uddg=" in href:
                import urllib.parse
                parsed = urllib.parse.urlparse(href)
                qs = urllib.parse.parse_qs(parsed.query)
                href = qs.get("uddg", [href])[0]
                href = urllib.parse.unquote(href)
            snippet = ""
            if i + 1 < len(rows):
                next_row = rows[i + 1]
                snippet_el = next_row.select_one("td.result-snippet")
                if snippet_el:
                    snippet = snippet_el.get_text(" ", strip=True)
            if title and href:
                results.append({"title": title, "url": href, "snippet": snippet})
        return json.dumps(results[:max_results], ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def fetch_page(url: str, timeout: float = 30.0) -> str:
    try:
        if isinstance(timeout, str):
            timeout = float(timeout) if timeout.strip() else 30.0
    except ValueError:
        timeout = 30.0
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines[:250])
    finally:
        await page.close()
