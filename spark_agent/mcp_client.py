"""Minimal synchronous MCP client for talking to the ``task_mcp`` server.

Spark is a *client* of the task system: it never imports ``task_program``.
Instead it spawns ``python -m task_mcp`` over stdio and invokes its tools. Each
``call_tool`` opens a short-lived session (own subprocess) — fine for a one-shot
background run, and it keeps the blocking LLM call cleanly outside any event loop.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


_SERVER = StdioServerParameters(command=sys.executable, args=["-m", "task_mcp"])


def _unwrap(result: Any) -> Any:
    """Pull the Python value out of an MCP CallToolResult.

    FastMCP returns structured content for dict/list returns and a text block
    for strings (our tools return ``"Error: ..."`` strings on failure)."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        # FastMCP wraps non-dict returns (e.g. lists) under a "result" key.
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured

    content = getattr(result, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
    return None


async def _call(name: str, arguments: dict[str, Any]) -> Any:
    async with stdio_client(_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return _unwrap(result)


def call_tool(name: str, **arguments: Any) -> Any:
    """Invoke a ``task_mcp`` tool by name. ``None`` arguments are dropped so the
    tool's own defaults apply."""
    clean = {k: v for k, v in arguments.items() if v is not None}
    return asyncio.run(_call(name, clean))
