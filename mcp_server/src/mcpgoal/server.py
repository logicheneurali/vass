from contextvars import ContextVar
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mcpgoal.config import ServerConfig
from mcpgoal.logging_.logger import RequestLogger
from mcpgoal.middleware.acl import check_access
from mcpgoal.tools import calculator, datetime_, executor, filesystem, web
from mcpgoal.tools.disk_space import get_disk_space as _disk_space
from mcpgoal.tools.vasscript import execute_vasscript as _vasscript
from mcpgoal.tools.vasscript import execute_code as _exec_code
from mcpgoal.tools.vasscript import info_read as _info_read
from mcpgoal.tools.vasscript import info_write as _info_write
from mcpgoal.tools.vasscript import clipboard_get as _clip_get
from mcpgoal.tools.vasscript import clipboard_set as _clip_set
from mcpgoal.tools.playwright import search_web as _search_web
from mcpgoal.tools.playwright import fetch_page as _fetch_page
from mcpgoal.tools.langcheck import check_language as _check_language

client_ip_var: ContextVar[str] = ContextVar("client_ip", default="unknown")
_loggers: dict[str, RequestLogger] = {}


def _get_logger(ip: str, log_dir: str) -> RequestLogger:
    if ip not in _loggers:
        _loggers[ip] = RequestLogger(ip, log_dir)
    return _loggers[ip]


async def _tool(name: str, params_str: str, coro, config: ServerConfig):
    ip = client_ip_var.get()
    if not check_access(name, ip, config):
        raise PermissionError(f"Access denied for tool '{name}' from {ip}")
    logger = _get_logger(ip, config.log_dir)
    try:
        result = await coro
        logger.log(name, params_str, "ok", result)
        return result
    except TypeError as e:
        syntax = _TOOL_SYNTAX.get(name, f"{name}(...)")
        msg = f"SYNTAX ERROR: {e}. Correct syntax: {syntax}"
        logger.log(name, params_str, "syntax_error", msg)
        return msg
    except Exception as e:
        logger.log(name, params_str, "error", str(e))
        raise


_TOOL_SYNTAX = {
    "browse": "browse(url) — example: browse('https://example.com')",
    "read_file": "read_file(path) — example: read_file('events.json')",
    "write_file": "write_file(path, content) — example: write_file('events.json', '{...}')",
    "current_time": "current_time() — no parameters",
    "calculate": "calculate(expression) — example: calculate('2+2')",
    "execute": "execute(command) — example: execute('ping localhost')",
    "disk_space": "disk_space() — no parameters",
    "script": "script(script_name) — example: script('eventi') or script('?') to list",
    "interact": "interact(code) — example: interact(\"say('hello')\")",
    "readinfo": "readinfo(id) — example: readinfo('1780394454383')",
    "writeinfo": "writeinfo(text) — example: writeinfo('dati da salvare')",
    "clipboardget": "clipboardget() — no parameters",
    "clipboardset": "clipboardset(text) — example: clipboardset('testo')",
    "websearch": "websearch(query) — example: websearch('latest news')",
    "webfetch": "webfetch(url) — example: webfetch('https://example.com')",
}


def create_server(config: ServerConfig) -> FastMCP:
    mcp = FastMCP("MCPGoal")
    mcp.settings.streamable_http_path = "/"

    ref_path = Path(__file__).resolve().parent.parent.parent.parent / "Allowed_root" / "VASCRIPT_REFERENCE.md"
    try:
        _interact_doc = ref_path.read_text(encoding="utf-8")
    except Exception:
        _interact_doc = "Execute VASScript code. Full reference: read_file('VASCRIPT_REFERENCE.md')"

    @mcp.tool()
    async def browse(url: str) -> str:
        """Fetch content from a URL and extract readable text. Use for reading web pages."""
        return await _tool("browse", f"url={url}", web.browse(url), config)

    @mcp.tool()
    async def read_file(path: str) -> str:
        """Read ANY file from Allowed_root. Use for memory.json, events.json, schedule.json, VASCRIPT_REFERENCE.md. Provide just the filename."""
        return await _tool("read_file", f"path={path}", filesystem.read_file(path, config.allowed_root), config)

    @mcp.tool()
    async def write_file(path: str, content: str) -> str:
        """Write content to a file in the Allowed_root directory."""
        return await _tool("write_file", f"path={path}", filesystem.write_file(path, content, config.allowed_root), config)

    @mcp.tool()
    async def current_time() -> str:
        """Get the current date and time."""
        return await _tool("current_time", "", datetime_.current_time(), config)

    @mcp.tool()
    async def calculate(expression: str) -> str:
        """Evaluate a mathematical expression."""
        return await _tool("calculate", f"expr={expression}", calculator.calculate(expression), config)

    @mcp.tool()
    async def execute(command: str) -> str:
        """Execute a system command. Only allowed commands from the configured whitelist can be run."""
        return await _tool("execute", f"cmd={command}", executor.execute(command, config.allowed_commands), config)

    @mcp.tool()
    async def disk_space() -> str:
        """Get available disk space information."""
        return await _tool("disk_space", "", _disk_space(), config)

    @mcp.tool()
    async def script(script_name: str) -> str:
        """Execute a VASScript file from the scripts folder (without .vass extension). Call with '?' to list available scripts."""
        return await _tool("script", f"script={script_name}", _vasscript(script_name), config)

    async def _interact_handler(code: str) -> str:
        return await _tool("interact", f"len={len(code)}", _exec_code(code), config)
    _interact_handler.__doc__ = _interact_doc
    interact = mcp.tool()(_interact_handler)

    @mcp.tool()
    async def readinfo(id: str) -> str:
        """Read an info/memory file by its numeric ID. NOT for reading memory.json — use read_file('memory.json') instead."""
        return await _tool("readinfo", f"id={id}", _info_read(id), config)

    @mcp.tool()
    async def writeinfo(text: str) -> str:
        """Write text to a new info file. Returns the file ID (timestamp)."""
        return await _tool("writeinfo", f"len={len(text)}", _info_write(text), config)

    @mcp.tool()
    async def clipboardget() -> str:
        """Get the current clipboard text content."""
        return await _tool("clipboardget", "", _clip_get(), config)

    @mcp.tool()
    async def clipboardset(text: str) -> str:
        """Set the clipboard text content."""
        return await _tool("clipboardset", f"len={len(text)}", _clip_set(text), config)

    @mcp.tool()
    async def websearch(query: str) -> str:
        """Search the web using DuckDuckGo. Returns top results with title, URL, and snippet in JSON."""
        return await _tool("websearch", f"q={query[:80]}", _search_web(query), config)

    @mcp.tool()
    async def webfetch(url: str) -> str:
        """Fetch a web page using headless Chromium (Playwright). Extracts rendered text content from JavaScript pages."""
        return await _tool("webfetch", f"url={url[:100]}", _fetch_page(url), config)

    @mcp.tool()
    async def langcheck(text: str, lang: str = "it") -> str:
        """Validate text against Tier 2 linguistic rules (morphology, syntax) for the given language."""
        return await _tool("langcheck", f"lang={lang} len={len(text)}", _check_language(text, lang), config)

    return mcp
