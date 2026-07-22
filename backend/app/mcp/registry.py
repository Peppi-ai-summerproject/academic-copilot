from mcp.server.fastmcp import FastMCP

from app.mcp.tools.health import ping
from app.mcp.tools.student import get_student


def register_tools(server: FastMCP) -> None:
    """Register all available MCP tools."""

    server.add_tool(
        ping,
        name="ping",
        description="Simple health check for the MCP server.",
    )

    server.add_tool(
        get_student,
        name="get_student",
        description=(
            "Retrieve a student profile from the simulated Peppi database "
            "using the student's numeric database ID."
        ),
    )