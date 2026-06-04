import json
import urllib.request


class McpClient:
    def __init__(self, url, timeout=10):
        self.url = url
        self.timeout = timeout
        self._req_id = 0
        self._session_id = None
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream, */*",
            "User-Agent": "vass-mcp-client/1.0"
        }

    def _next_id(self):
        self._req_id += 1
        return self._req_id

    def _post(self, body):
        h = dict(self._headers)
        if self._session_id:
            h["mcp-session-id"] = self._session_id
        req = urllib.request.Request(self.url, data=body, headers=h)
        resp = urllib.request.urlopen(req, timeout=self.timeout)
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        raw = resp.read().decode()
        return raw

    def _parse_sse(self, raw):
        for line in raw.split("\n"):
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise Exception("MCP: no SSE data event in response")

    def _send(self, method, params=None):
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {}
        }).encode()
        raw = self._post(body)
        data = self._parse_sse(raw)
        if "error" in data:
            raise Exception(f"MCP error: {data['error']}")
        return data.get("result")

    def initialize(self):
        return self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "vass", "version": "1.0"}
        })

    def get_tools(self):
        result = self._send("tools/list")
        tools = []
        for t in result.get("tools", []):
            tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("inputSchema", {})
                }
            })
        return tools

    def call_tool(self, name, arguments):
        return self._send("tools/call", {"name": name, "arguments": arguments})
