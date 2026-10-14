"""Call one MCP tool directly, for the orchestration code around the agents.

The agents reach the shop through their toolset; the runner and the FastAPI
backend sometimes need the same facts (what is on the board, what the shop's
date is) without paying for a model call.  Those calls go through **this same
MCP server**, launched from the same ``.mcp.json`` entry, rather than opening
the database directly — so there is still exactly one tools layer over the shop.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from config import mcp_command


def _transport() -> StdioTransport:
    """Build the stdio transport from the project's .mcp.json entry.

    Paths come back absolute, so this works whatever directory the caller was
    started from.
    """
    command, args = mcp_command()
    return StdioTransport(command=command, args=args)


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Call ``name`` on the campus-customs MCP server and return its parsed result."""
    async with Client(_transport()) as client:
        result = await client.call_tool(name, arguments or {})
        return result.data
