"""Browser automation MCP tools — stateful Playwright browser session."""
import json
import os


async def browser_open(url: str) -> str:
    """Navigate to a URL in the persistent browser session. Stay on the same page.
    Returns page title and text content. Use this to start browsing or navigate to a new page.
    Args: url (full URL including https://)"""
    import asyncio
    from .playwright import _get_page
    page = await _get_page()
    loading = False
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    except Exception:
        # Navigation may time out waiting for slow resources, but the page
        # could still be opening. Do not fail — wait and try to read content.
        loading = True
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    await asyncio.sleep(2)
    try:
        title = await page.title()
        text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return json.dumps({
            "title": title,
            "url": page.url,
            "text": "\n".join(lines[:100]),
            "loading": loading,
        }, ensure_ascii=False)
    except Exception:
        return json.dumps({
            "title": "",
            "url": page.url,
            "text": "",
            "loading": True,
        }, ensure_ascii=False)


async def browser_read() -> str:
    """Read the text content of the current page. Use this to see what's visible on the page
    after navigating or interacting."""
    from .playwright import _get_page
    page = await _get_page()
    text = await page.evaluate("() => document.body.innerText")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return json.dumps({
        "url": page.url,
        "title": await page.title(),
        "text": "\n".join(lines[:100]),
    }, ensure_ascii=False)


async def browser_click(text: str) -> str:
    """Click an element containing the specified text. Finds the first match on the current page.
    Use for buttons, links, or clickable elements. Use exact or partial visible text.
    Args: text (visible text of the element to click, e.g. 'Login', 'Submit', 'Download')"""
    from .playwright import _get_page
    page = await _get_page()
    try:
        await page.get_by_role("button", name=text).first.click(timeout=5000)
    except Exception:
        try:
            await page.get_by_role("link", name=text).first.click(timeout=5000)
        except Exception:
            await page.get_by_text(text, exact=False).first.click(timeout=10000)
    return json.dumps({"clicked": text, "url": page.url, "ok": True}, ensure_ascii=False)


async def browser_fill(label: str, value: str) -> str:
    """Fill an input field by its label text. Finds the input associated with a label element.
    Use for typing into form fields. Also works with placeholder text.
    Args: label (label text near the field, or placeholder text), value (text to type)"""
    from .playwright import _get_page
    page = await _get_page()
    try:
        await page.get_by_label(label, exact=False).first.fill(value, timeout=10000)
    except Exception:
        await page.get_by_placeholder(label).first.fill(value, timeout=10000)
    return json.dumps({"filled": label, "value": value, "ok": True}, ensure_ascii=False)


async def browser_submit() -> str:
    """Submit the current form. Clicks the first submit button on the page.
    Use after filling form fields with browser_fill()."""
    from .playwright import _get_page
    page = await _get_page()
    await page.locator("button[type='submit'], input[type='submit']").first.click(timeout=10000)
    return json.dumps({"submitted": True, "url": page.url, "ok": True}, ensure_ascii=False)


async def browser_download(text: str) -> str:
    """Click a link/button and download the file. Saves to Allowed_root/downloads/.
    Returns the filename. Wait for download to complete before returning.
    Args: text (visible text of the link/button to click for download)"""
    from .playwright import _get_page
    page = await _get_page()
    async with page.expect_download(timeout=30000) as download_info:
        await page.get_by_text(text, exact=False).first.click(timeout=10000)
    download = await download_info.value
    dl_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))), "Allowed_root", "downloads")
    os.makedirs(dl_dir, exist_ok=True)
    path = os.path.join(dl_dir, download.suggested_filename)
    await download.save_as(path)
    return json.dumps({"downloaded": download.suggested_filename, "path": path, "ok": True}, ensure_ascii=False)


async def browser_back() -> str:
    """Go back to the previous page. Use to navigate backwards in the browsing history."""
    from .playwright import _get_page
    page = await _get_page()
    await page.go_back(timeout=10000)
    return json.dumps({"url": page.url, "ok": True}, ensure_ascii=False)


async def browser_show() -> str:
    """Open the current page in a VISIBLE browser window so the user can interact.
    Use this when the user needs to manually log in, solve a CAPTCHA, or fill a complex form.
    The session (cookies, logins) is saved automatically and reused in headless mode."""
    from .playwright import _get_visible_page
    page = await _get_visible_page()
    return json.dumps({
        "visible": True, "url": page.url,
        "message": "Browser window opened. Complete your login and then type 'continue'.",
    }, ensure_ascii=False)


async def browser_check_auth(text: str) -> str:
    """Check if the user is authenticated by searching for expected text on the page.
    Use after a login step to verify success. Look for dashboard text, welcome message, or logout link.
    Args: text (expected text visible after successful login, e.g. 'Dashboard', 'Welcome', 'Logout')"""
    from .playwright import _get_page
    page = await _get_page()
    content = await page.evaluate("() => document.body.innerText")
    authenticated = text.lower() in content.lower()
    return json.dumps({
        "authenticated": authenticated,
        "url": page.url,
        "checked_text": text,
    }, ensure_ascii=False)
