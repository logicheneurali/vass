"""MCP server running in-process as a daemon thread."""
import asyncio
import logging
import os
import sys
import threading
from pathlib import Path

_MCP_LOG = None


def _setup_mcp_log():
    global _MCP_LOG
    if _MCP_LOG is not None:
        return
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "log")
    os.makedirs(log_dir, exist_ok=True)
    _MCP_LOG = logging.getLogger("mcp")
    _MCP_LOG.setLevel(logging.INFO)
    _MCP_LOG.propagate = False
    log_path = os.path.join(log_dir, "mcp.log")
    with open(log_path, "w", encoding="utf-8") as _f:
        _f.write("")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _MCP_LOG.addHandler(fh)


class McpServerThread(threading.Thread):
    def __init__(self, mcp_port=9988, allow_scripts=False, debug=False):
        super().__init__(daemon=True, name="mcp-server")
        self._port = mcp_port
        self._allow_scripts = allow_scripts
        self._debug = debug

    def run(self):
        _setup_mcp_log()
        _mcp_src = str(Path(__file__).resolve().parent.parent / "mcp_server" / "src")
        if _mcp_src not in sys.path:
            sys.path.insert(0, _mcp_src)
        if self._debug:
            os.environ["VASS_DEBUG"] = "1"
        try:
            from mcpgoal.config import load_config
            from mcpgoal.server import create_server
            from mcpgoal.main import _cors_middleware, _client_ip_middleware
            import uvicorn
        except Exception as e:
            _MCP_LOG.error(f"MCP import failed: {e}")
            return
        try:
            config = load_config()
            config.allow_scripts = self._allow_scripts
            mcp = create_server(config)
            http_app = mcp.streamable_http_app()
            wrapped = _cors_middleware(_client_ip_middleware(http_app))
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access",
                         "mcp", "mcp.server"):
                logging.getLogger(name).setLevel(logging.ERROR)
            _MCP_LOG.info(f"Starting on http://127.0.0.1:{self._port}")
            uvicorn.run(wrapped, host="127.0.0.1", port=self._port,
                        log_level="error", access_log=False, log_config=None)
        except Exception as e:
            _MCP_LOG.error(f"MCP server error: {e}")
