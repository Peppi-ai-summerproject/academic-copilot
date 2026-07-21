from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.mcp.tools.health import ping


def register_tools(server: FastMCP) -> None:
    """Register all tools exposed by the Academic Copilot MCP server.

    Tool implementations should remain independent from the MCP server and
    delegate academic business logic to application services.
    """

    server.add_tool(
        ping,
        name="ping",
        description="Simple health check for the MCP server.",
    )