import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse


async def browse(url: str, timeout: float = 60.0) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
    headers = {
        "User-Agent": "MCPGoal/1.0 (research assistant)"
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            return resp.text
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line for line in text.splitlines() if line.strip()]
        return "\n".join(lines[:200])
