from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.mcp.tools.health import ping


def register_tools(server: FastMCP) -> None:
    """Register the MCP tools supported by this server.

    Add future tool functions here. Tool implementations must remain decoupled
    from the server and delegate academic work to application services.
    """
    server.add_tool(
        ping,
        name="ping",
        description="Simple health check for the MCP server.",
    )
