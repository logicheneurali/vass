import logging
import uvicorn

from mcpgoal.config import load_config
from mcpgoal.server import client_ip_var, create_server


def _client_ip_middleware(app):
    """Raw ASGI middleware to capture client IP — compatible with streaming responses."""
    async def asgi_app(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        client = scope.get("client")
        ip = client[0] if client else "unknown"

        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for")
        if forwarded:
            ip = forwarded.decode().split(",")[0].strip()

        token = client_ip_var.set(ip)
        try:
            await app(scope, receive, send)
        finally:
            client_ip_var.reset(token)

    return asgi_app


def _cors_middleware(app):
    """Add CORS headers for cross-origin browser clients."""
    async def asgi_app(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers.setdefault(b"access-control-allow-origin", b"http://localhost:9988")
                headers.setdefault(b"access-control-allow-methods", b"GET, POST, OPTIONS")
                headers.setdefault(b"access-control-allow-headers", b"*")
                headers.setdefault(b"access-control-expose-headers", b"*")
                message["headers"] = list(headers.items())
            await send(message)

        if scope["method"] == "OPTIONS":
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"access-control-allow-origin", b"http://localhost:9988"),
                    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                    (b"access-control-allow-headers", b"*"),
                    (b"access-control-max-age", b"86400"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        await app(scope, receive, send_wrapper)

    return asgi_app


def main() -> None:
    config = load_config()
    mcp = create_server(config)
    http_app = mcp.streamable_http_app()

    wrapped = _cors_middleware(_client_ip_middleware(http_app))

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "mcp", "mcp.server"):
        logging.getLogger(name).setLevel(logging.WARNING)

    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "[MCP] %(levelname)s %(message)s"
    log_config["formatters"]["access"]["fmt"] = "[MCP] %(levelname)s %(message)s"
    log_config["loggers"]["uvicorn.access"]["handlers"] = []

    print("[MCP] Starting on http://127.0.0.1:9988")
    uvicorn.run(wrapped, host="127.0.0.1", port=9988, log_level="warning", access_log=False, log_config=log_config)


if __name__ == "__main__":
    main()
