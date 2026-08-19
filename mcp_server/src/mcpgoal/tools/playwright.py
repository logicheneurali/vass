import json
import os
import time

from playwright.async_api import async_playwright

_browser = None
_playwright = None
_context = None
_page = None


async def _get_browser():
    global _browser, _playwright
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=os.environ.get("VASS_DEBUG", "0") != "1",
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
    return _browser


async def _get_page():
    global _context, _page, _playwright
    if _context is None:
        _playwright = await async_playwright().start()
        user_data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))), "Allowed_root", "browser_profile")
        os.makedirs(user_data_dir, exist_ok=True)
        _context = await _playwright.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
            accept_downloads=True,
            no_viewport=True,
        )
    else:
        try:
            # Check if context is still alive
            _context.pages
        except Exception:
            # Context was closed (e.g., user closed visible browser)
            _context = None
            _page = None
            return await _get_page()
    if _page is None or _page.is_closed():
        _page = await _context.new_page()
    return _page


async def _get_visible_page():
    global _context, _page, _playwright
    # Save current URL before closing
    current_url = _page.url if _page and not _page.is_closed() else "about:blank"
    if _context:
        await _context.close()
        _context = None
        _page = None
    user_data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))), "Allowed_root", "browser_profile")
    _playwright = await async_playwright().start()
    _context = await _playwright.chromium.launch_persistent_context(
        user_data_dir,
        headless=False,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        accept_downloads=True,
        no_viewport=True,
    )
    _page = await _context.new_page()
    if current_url != "about:blank":
        await _page.goto(current_url, timeout=30000, wait_until="domcontentloaded")
    return _page


async def search_web(query: str, max_results: int = 10) -> str:
    """Search the web with automatic engine rotation when engines block bots.
    Returns JSON array of {title, url, snippet}."""
    try:
        if isinstance(max_results, str):
            max_results = int(max_results) if max_results.strip() else 10
    except ValueError:
        max_results = 10
    order = _engine_order()
    now = time.time()
    for name in order:
        state = _engine_state.get(name)
        if state and state["blocked_until"] > now:
            continue
        engine = _ENGINES.get(name)
        if not engine:
            continue
        try:
            results, blocked = await engine(query, max_results)
        except Exception as e:
            print(f"[Search] {name} error: {e}")
            blocked, results = False, []
        if results:
            _engine_state.pop(name, None)
            global _last_ok
            _last_ok = name
            return json.dumps(results, ensure_ascii=False, indent=2)
        if blocked:
            streak = state["fail_streak"] + 1 if state else 1
            _engine_state[name] = {
                "blocked_until": now + min(_BASE_COOLDOWN * streak, _MAX_COOLDOWN),
                "fail_streak": streak,
            }
            print(f"[Search] {name} blocked by anti-bot, cooling down "
                  f"{streak * _BASE_COOLDOWN // 60}min")
    return json.dumps({"error": "all search engines blocked or failed"}, ensure_ascii=False)


# ── Search engine rotation (anti-bot) ──────────────────────────────────

_BASE_COOLDOWN = 15 * 60          # seconds, grows per consecutive block
_MAX_COOLDOWN = 120 * 60
_engine_state = {}                 # name -> {"blocked_until": ts, "fail_streak": n}
_last_ok = None                    # last engine that returned results

_BLOCK_MARKERS = (
    "captcha",
    "complete the following challenge",
    "select all squares containing a duck",
    "verifying your browser",
    "checking your browser",
    "unusual traffic",
    "you have been blocked",
    "i'm not a robot",
    "access denied",
)
_BLOCK_STATUSES = {202, 403, 418, 429, 500, 503}


def _is_blocked_page(status, text):
    """True only if the page is a block/challenge page (no results expected)."""
    if status in _BLOCK_STATUSES:
        return True
    low = (text or "").lower()
    return any(m in low for m in _BLOCK_MARKERS)


def _ddg_uddg(href):
    """Resolve DuckDuckGo 'uddg=' redirect param to the real URL."""
    if "uddg=" in href:
        import urllib.parse
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        href = qs.get("uddg", [href])[0]
        href = urllib.parse.unquote(href)
    return href


def _bing_url(href):
    """Resolve Bing redirect URL from the base64 'u=a1' query param."""
    import base64
    import re
    m = re.search(r"[?&]u=a1([A-Za-z0-9+/=_-]+)", href)
    if not m:
        return href
    enc = m.group(1).replace("-", "+").replace("_", "/")
    try:
        return base64.b64decode(enc + "===").decode("utf-8", "ignore")
    except Exception:
        return href


async def _http_get(url, params=None):
    import httpx
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        return await client.get(url, params=params, headers=headers)


async def _bing_search(query, max_results):
    from bs4 import BeautifulSoup
    r = await _http_get("https://www.bing.com/search", {"q": query})
    soup = BeautifulSoup(r.text, "lxml")
    results = []
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = _bing_url(a.get("href", ""))
        snippet_el = li.select_one("p, .b_caption")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if title and href:
            results.append({"title": title, "url": href, "snippet": snippet})
    if results:
        return results[:max_results], False
    return [], _is_blocked_page(r.status_code, r.text)


async def _ddg_lite_search(query, max_results):
    from bs4 import BeautifulSoup
    r = await _http_get("https://lite.duckduckgo.com/lite/", {"q": query})
    soup = BeautifulSoup(r.text, "lxml")
    results = []
    rows = soup.select("table tr")
    for i, row in enumerate(rows):
        link_el = row.select_one("a.result-link")
        if not link_el:
            continue
        title = link_el.get_text(strip=True)
        href = _ddg_uddg(link_el.get("href", ""))
        snippet = ""
        if i + 1 < len(rows):
            next_row = rows[i + 1]
            snippet_el = next_row.select_one("td.result-snippet")
            if snippet_el:
                snippet = snippet_el.get_text(" ", strip=True)
        if title and href:
            results.append({"title": title, "url": href, "snippet": snippet})
    if results:
        return results[:max_results], False
    return [], _is_blocked_page(r.status_code, r.text)


async def _ddg_html_search(query, max_results):
    from bs4 import BeautifulSoup
    r = await _http_get("https://html.duckduckgo.com/html/", {"q": query})
    soup = BeautifulSoup(r.text, "lxml")
    results = []
    for item in soup.select(".result"):
        a = item.select_one("a.result__a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = _ddg_uddg(a.get("href", ""))
        snippet_el = item.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if title and href:
            results.append({"title": title, "url": href, "snippet": snippet})
    if results:
        return results[:max_results], False
    return [], _is_blocked_page(r.status_code, r.text)


async def _mojeek_search(query, max_results):
    from bs4 import BeautifulSoup
    r = await _http_get("https://www.mojeek.com/search", {"q": query})
    soup = BeautifulSoup(r.text, "lxml")
    results = []
    for li in soup.select("ul.results li"):
        a = li.select_one("h2 a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href", "")
        snippet_el = li.select_one("p")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if title and href:
            results.append({"title": title, "url": href, "snippet": snippet})
    if results:
        return results[:max_results], False
    return [], _is_blocked_page(r.status_code, r.text)


async def _ddg_playwright_search(query, max_results):
    """DDG via real browser — bypasses most anti-bot, but DDG may still block."""
    import urllib.parse
    from bs4 import BeautifulSoup
    browser = await _get_browser()
    page = await browser.new_page()
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        results = []
        for item in soup.select(".result"):
            a = item.select_one("a.result__a")
            if not a:
                continue
            title = a.get_text(strip=True)
            href = _ddg_uddg(a.get("href", ""))
            snippet_el = item.select_one(".result__snippet")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            if title and href:
                results.append({"title": title, "url": href, "snippet": snippet})
        if results:
            return results[:max_results], False
        return [], _is_blocked_page(200, html)
    finally:
        await page.close()


_ENGINES = {
    "bing": _bing_search,
    "ddg_lite": _ddg_lite_search,
    "ddg_html": _ddg_html_search,
    "mojeek": _mojeek_search,
    "ddg_playwright": _ddg_playwright_search,
}


def _engine_order():
    """Round-robin with last-known-good first (if not cooling down)."""
    now = time.time()
    names = list(_ENGINES.keys())
    if _last_ok and _last_ok in names and not (_engine_state.get(_last_ok, {}) or {}).get("blocked_until", 0) > now:
        names.remove(_last_ok)
        names.insert(0, _last_ok)
    return names


async def fetch_page(url: str, timeout: float = 90.0) -> str:
    try:
        if isinstance(timeout, str):
            timeout = float(timeout) if timeout.strip() else 90.0
    except ValueError:
        timeout = 90.0

    from .web import browse
    try:
        text = await browse(url, timeout=30)
        if len(text) > 500:
            return text
    except Exception:
        pass

    try:
        browser = await _get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            text = await page.evaluate("() => document.body.innerText")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            return "\n".join(lines[:250])
        finally:
            await page.close()
    except Exception as e:
        try:
            return await browse(url, timeout * 2)
        except Exception as e2:
            return f"Failed to fetch {url}: {e}"
