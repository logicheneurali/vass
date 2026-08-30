import json
import os
import re
import time
from urllib.parse import quote

from playwright.async_api import async_playwright

_browser = None
_playwright = None
_context = None
_page = None

# ── Anti-detection stealth ─────────────────────────────────────────
# Overrides the automation fingerprints that anti-bot systems check:
# navigator.webdriver, window.chrome, navigator.plugins, languages and
# permission query behavior. Applied via add_init_script so every new
# page (including popups) inherits the patch.
_STEALTH_JS = """
(() => {
  // navigator.webdriver -> undefined
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  // window.chrome -> present with typical keys
  try {
    if (!window.chrome) {
      const mk = (name) => ({ [name]: () => {} });
      window.chrome = {
        runtime: mk('connect'), csi: () => {}, loadTimes: () => {},
        app: mk('isInstalled'), webstore: mk('install'),
      };
    }
  } catch (e) {}
  // navigator.plugins -> non-empty fake list
  try {
    const mkPlugin = (name, file, desc) => {
      const p = { name, filename: file, description: desc,
                  length: 1, 0: { type: 'application/pdf' } };
      return p;
    };
    Object.defineProperty(navigator, 'plugins', {
      get: () => [
        mkPlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
        mkPlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
        mkPlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      ],
    });
  } catch (e) {}
  // navigator.languages -> consistent with an Italian profile
  try {
    Object.defineProperty(navigator, 'languages', { get: () => ['it-IT', 'it', 'en-US', 'en'] });
  } catch (e) {}
  // permissions.query -> resolve common permissions as 'prompt'/'granted'
  try {
    const orig = navigator.permissions && navigator.permissions.query;
    if (orig) {
      navigator.permissions.query = (p) => {
        const name = (p && p.name) || '';
        const always = ['notifications', 'geolocation', 'clipboard-read',
                        'clipboard-write', 'midi', 'background-sync'];
        const res = always.includes(name)
          ? { state: 'granted', onchange: null }
          : { state: 'prompt', onchange: null };
        return Promise.resolve(res);
      };
    }
  } catch (e) {}
  // window sizing consistency (outer vs inner)
  try {
    if (window.outerWidth && window.innerWidth &&
        window.outerWidth - window.innerWidth > 100) {
      Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth + 4 });
      Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 100 });
    }
  } catch (e) {}
})();
"""

_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-automation",
    "--no-first-run",
    "--no-default-browser-check",
]


async def _apply_stealth(context):
    """Inject the stealth init script into a BrowserContext or Page."""
    try:
        await context.add_init_script(_STEALTH_JS)
    except Exception as e:
        print(f"[Search] stealth inject failed: {e}")


async def _new_stealth_page(browser):
    """Create a page from a Browser and apply the stealth init script."""
    page = await browser.new_page()
    try:
        await page.add_init_script(_STEALTH_JS)
    except Exception as e:
        print(f"[Search] page stealth inject failed: {e}")
    return page


async def _get_browser():
    global _browser, _playwright
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=os.environ.get("VASS_DEBUG", "0") != "1",
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"] + _STEALTH_ARGS,
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
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"] + _STEALTH_ARGS,
            accept_downloads=True,
            no_viewport=True,
        )
        await _apply_stealth(_context)
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
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"] + _STEALTH_ARGS,
        accept_downloads=True,
        no_viewport=True,
    )
    await _apply_stealth(_context)
    _page = await _context.new_page()
    if current_url != "about:blank":
        await _page.goto(current_url, timeout=30000, wait_until="domcontentloaded")
    return _page


async def search_web(query: str, max_results: int = 10, page: int = 1) -> str:
    """Search the web with automatic engine rotation when engines block bots.
    Returns JSON array of {title, url, snippet}. For site:<domain> queries it
    queries the site's own search form directly; page (>=1) selects the result
    page for sites that support pagination."""
    try:
        if isinstance(max_results, str):
            max_results = int(max_results) if max_results.strip() else 10
        if isinstance(page, str):
            page = int(page) if page.strip() else 1
    except ValueError:
        max_results = 10
    if page < 1:
        page = 1
    # Direct site search: site:<domain> queries bypass the engines and query
    # the site's own search form via a live browser. The result is rendered
    # text (robust to card markup changes), or an explicit reformulation hint
    # for the AI when the site has no discoverable search form.
    site = _match_site_query(query)
    if site:
        direct = await _direct_site_search(site[0], site[1], page)
        if direct is not None:
            return direct
        print(f"[Search] site {site[0]} direct search failed, engine fallback")
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


async def _http_get(url, params=None):
    import httpx
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        return await client.get(url, params=params, headers=headers)


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


async def _brave_search(query, max_results):
    """Brave Search via plain HTTP. Returns {title, url, snippet} from div.snippet
    containers. Brave rate-limits with HTTP 429, which the engine rotation treats
    as a block (cooldown) like the other engines."""
    from bs4 import BeautifulSoup
    r = await _http_get("https://search.brave.com/search", {"q": query, "source": "web"})
    soup = BeautifulSoup(r.text, "lxml")
    results = []
    for sn in soup.select("div.snippet"):
        a = sn.select_one("a[href*='http']")
        if not a:
            continue
        href = a.get("href", "")
        title_el = sn.select_one(".snippet-title, .title, a[title]")
        title = title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True)
        desc_el = sn.select_one(".snippet-description")
        snippet = desc_el.get_text(" ", strip=True) if desc_el else ""
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
    page = await _new_stealth_page(browser)
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
    "brave": _brave_search,
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


# ── Direct site search (site:<domain> queries) ─────────────────────────

_SITE_RE = re.compile(r"site:\s*([a-zA-Z0-9.-]+)")
_SITE_MAX_LINES = 1000

# Cookie-consent / banner dismissal: buttons whose text signals "accept all".
# Generic across EU sites; if none matches, extraction proceeds unchanged.


def _match_site_query(query):
    """Return (domain, terms) if the query targets a specific site, else None."""
    m = _SITE_RE.search(query or "")
    if not m:
        return None
    domain = m.group(1).strip().lower().lstrip(".")
    terms = _SITE_RE.sub("", query).strip()
    return (domain, terms)


async def _dismiss_cookie_banner(page):
    """Click a cookie/consent 'accept' button if present, so the consent overlay
    does not dominate the extracted page text. Best-effort; never raises."""
    try:
        # Amazon uses <input value="Accetta">; most sites use <button>/<a>.
        clicked = await page.evaluate("""() => {
            const sel = 'button, input[type="submit"], input[type="button"], a, [role="button"]';
            const rx = /accetta\\s*(tutti|tutto)?|accept\\s*(all|everything)?|ok|consent/i;
            for (const el of document.querySelectorAll(sel)) {
                const t = (el.value || el.textContent || '').trim();
                if (!t || t.length > 30) continue;
                if (rx.test(t) && !/cancella|rifiuta|decline|personalizza|customize/.test(t)) {
                    if (typeof el.click === 'function') el.click();
                    return true;
                }
            }
            return false;
        }""")
        if clicked:
            await page.wait_for_timeout(1500)
    except Exception:
        pass


async def _discover_search_form_http(domain):
    """Recon a site's homepage via plain HTTP (fast path) to find its search
    form: a <form> containing a search <input>. Returns (action, input_name)
    or None. This is the 'recon': we let the live site tell us how it
    accepts queries, so we never hardcode URL/selector structure that may
    change."""
    try:
        import httpx
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": "MCPGoal/1.0 (research assistant)"
        }
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(f"https://{domain}/", headers=headers)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:
        return None
    for form in soup.select("form"):
        inp = form.select_one(
            'input[type="search"], input[name*="q"], input[name*="search"], '
            'input[name*="keyword"], input[type="text"]')
        if inp and inp.get("name"):
            return (form.get("action") or "", inp["name"])
    return None


async def _discover_search_form(page, domain):
    """Playwright fallback recon for JS-heavy sites. Returns (action, input_name)
    or None."""
    try:
        await page.goto(f"https://{domain}/", timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1800)
    except Exception:
        return None
    form = await page.evaluate("""() => {
        const inputs = [
            'input[type="search"]',
            'input[name*="q"]',
            'input[name*="search"]',
            'input[name*="keyword"]',
            'input[type="text"]',
        ].join(',');
        for (const form of document.querySelectorAll('form')) {
            const inp = form.querySelector(inputs);
            if (!inp || !inp.name) continue;
            return { action: form.getAttribute('action') || '', name: inp.name };
        }
        return null;
    }""")
    return (form["action"], form["name"]) if form else None


def _build_site_query_url(domain, action, input_name, terms):
    base = action if action.startswith("http") else f"https://{domain}{action}"
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{input_name}={quote(terms)}"


def _trim_lines(text, max_lines):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return lines[:max_lines]


async def _direct_site_search(domain, terms, page=1):
    """Query a site's own search form with the given terms and return the
    page text (first _SITE_MAX_LINES). Strategy: fast plain-HTTP path first
    (works on Amazon/Euronics), Playwright fallback for JS-heavy sites.

    page >= 1 selects the result page; the pagination parameter is appended
    generically as &page=N (the common convention) so the AI can request more
    results without hardcoding site-specific URL formats.

    Returns None when the direct path cannot run (fetch failure) so the caller
    falls back to the engines. Returns an explicit reformulation hint for the
    AI when the site is reachable but has no discoverable search form."""
    if not terms:
        return None
    from .web import browse

    def _hint(reason):
        return (f"Recon on {domain}: {reason} Rephrase the request "
                f"(e.g. more generic terms) or name another site.")

    def _page_url(url):
        return f"{url}&page={page}" if page > 1 else url

    # Fast path: HTTP recon + HTTP query.
    form = await _discover_search_form_http(domain)
    if form:
        url = _build_site_query_url(domain, form[0], form[1], terms)
        try:
            text = await browse(_page_url(url), timeout=30, max_lines=_SITE_MAX_LINES)
            lines = _trim_lines(text, _SITE_MAX_LINES)
            if len(lines) >= 5:
                return f"[Search on {domain} for '{terms}'" + \
                       (f", page {page}" if page > 1 else "") + "]\n" + "\n".join(lines)
        except Exception:
            pass

    # Fallback: Playwright recon + rendered query.
    try:
        browser = await _get_browser()
    except Exception as e:
        print(f"[Search] site {domain}: browser error: {e}")
        return None
    pw_page = await _new_stealth_page(browser)
    try:
        try:
            form = await _discover_search_form(pw_page, domain)
        except Exception as e:
            print(f"[Search] site {domain}: recon error: {e}")
            return None
        if not form:
            return _hint("the site exposes no recognizable search form.")
        action, input_name = form
        try:
            await pw_page.goto(_page_url(_build_site_query_url(domain, action, input_name, terms)),
                               timeout=35000, wait_until="domcontentloaded")
            await pw_page.wait_for_timeout(2500)
        except Exception as e:
            print(f"[Search] site {domain}: query error: {e}")
            return None
        await _dismiss_cookie_banner(pw_page)
        text = await pw_page.evaluate("() => document.body.innerText")
        lines = _trim_lines(text, _SITE_MAX_LINES)
        if not lines:
            return _hint(f"no content returned for '{terms}'.")
        return f"[Search on {domain} for '{terms}'" + \
               (f", page {page}" if page > 1 else "") + "]\n" + "\n".join(lines)
    finally:
        await pw_page.close()


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
        page = await _new_stealth_page(browser)
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
