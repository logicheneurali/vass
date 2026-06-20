"""MCP server running in-process as a daemon thread."""
import asyncio
import logging
import sys
import threading
from pathlib import Path


class McpServerThread(threading.Thread):
    def __init__(self, mcp_port=9988, allow_scripts=False):
        super().__init__(daemon=True, name="mcp-server")
        self._port = mcp_port
        self._allow_scripts = allow_scripts

    def run(self):
        _mcp_src = str(Path(__file__).resolve().parent.parent / "mcp_server" / "src")
        if _mcp_src not in sys.path:
            sys.path.insert(0, _mcp_src)
        try:
            from mcpgoal.config import load_config
            from mcpgoal.server import create_server
            from mcpgoal.main import _cors_middleware, _client_ip_middleware
            import uvicorn
        except Exception as e:
            logging.getLogger("mcp").error(f"MCP import failed: {e}")
            return
        try:
            config = load_config()
            config.allow_scripts = self._allow_scripts
            mcp = create_server(config)
            http_app = mcp.streamable_http_app()
            wrapped = _cors_middleware(_client_ip_middleware(http_app))
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "mcp", "mcp.server"):
                logging.getLogger(name).setLevel(logging.ERROR)
            print(f"[MCP] Starting on http://127.0.0.1:{self._port}")
            import copy
            cfg = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
            cfg["formatters"]["default"]["fmt"] = "%(message)s"
            cfg["formatters"]["access"]["fmt"] = "%(message)s"
            uvicorn.run(wrapped, host="127.0.0.1", port=self._port,
                        log_level="error", access_log=False, log_config=cfg)
        except Exception as e:
            import traceback
            traceback.print_exc()
            logging.getLogger("mcp").error(f"MCP server error: {e}")
