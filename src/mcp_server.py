"""MCP server running in-process as a daemon thread."""
import asyncio
import logging
import sys
import threading
from pathlib import Path


class McpServerThread(threading.Thread):
    def __init__(self, mcp_port=9988):
        super().__init__(daemon=True, name="mcp-server")
        self._port = mcp_port

    def run(self):
        _mcp_src = str(Path(__file__).resolve().parent.parent / "mcp_server" / "src")
        if _mcp_src not in sys.path:
            sys.path.insert(0, _mcp_src)
        try:
            from mcpgoal.config import load_config as _load_config
            from mcpgoal.server import client_ip_var, create_server as _create_server
            from mcpgoal.main import _cors_middleware, _client_ip_middleware
            import uvicorn
        except Exception as e:
            logging.getLogger("mcp").error(f"MCP import failed: {e}")
            return

        try:
            config = _load_config()
            mcp = _create_server(config)
            http_app = mcp.streamable_http_app()
            wrapped = _cors_middleware(_client_ip_middleware(http_app))

            for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "mcp", "mcp.server"):
                logging.getLogger(name).setLevel(logging.ERROR)

            server = uvicorn.Server(uvicorn.Config(
                wrapped, host="127.0.0.1", port=self._port,
                log_level="error", access_log=False,
            ))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            print(f"[MCP] Starting on http://127.0.0.1:{self._port}")
            loop.run_until_complete(server.serve())
        except Exception as e:
            logging.getLogger("mcp").error(f"MCP server error: {e}")
