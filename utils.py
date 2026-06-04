import json
import subprocess
import time
from openai import APIConnectionError


def call_with_retry(fn, retries=4, delays=(1, 2, 4, 8), log_prefix="[AI]"):
    for attempt in range(retries):
        try:
            return fn()
        except APIConnectionError:
            if attempt == retries - 1:
                raise
            delay = delays[attempt]
            print(f"{log_prefix} Connessione fallita, riprovo tra {delay}s ({attempt+2}/{retries})")
            time.sleep(delay)


def execute_mcp_tool_calls(messages, msg, mcp, tools, openai_client, model, temperature=0.7, log_prefix="[AI]"):
    if not (msg.tool_calls and mcp and tools):
        return msg

    for tc in msg.tool_calls:
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            }]
        })
        try:
            args = json.loads(tc.function.arguments)
            result = mcp.call_tool(tc.function.name, args)
            if isinstance(result, dict) and "content" in result:
                parts = []
                for item in result["content"]:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                out = "\n".join(parts)
            else:
                out = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        except Exception as e:
            out = f"Errore: {e}"
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": out
        })

    resp = call_with_retry(lambda: openai_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        extra_body={"disable_thinking": True}
    ), log_prefix=log_prefix)
    return resp.choices[0].message


def init_mcp(mcp_server_url, timeout=120, log_prefix="[AI]"):
    if not mcp_server_url:
        return None, None
    from mcp_client import McpClient
    try:
        mcp = McpClient(mcp_server_url, timeout=timeout)
        mcp.initialize()
        tools = mcp.get_tools()
        print(f"{log_prefix} MCP initialized: {len(tools)} tools")
        return mcp, tools
    except Exception as e:
        print(f"{log_prefix} MCP init failed: {e}")
        return None, None
