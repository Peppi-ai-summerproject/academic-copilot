from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.core.logger import logger
from app.mcp.registry import register_tools

_SERVER: FastMCP | None = None


def create_server() -> FastMCP:
    """Create the MCP server instance and register the default tools."""
    global _SERVER

    if _SERVER is not None:
        return _SERVER

    server = FastMCP(
        name="academic-copilot-mcp",
        instructions="Academic Copilot MCP server for future academic tools.",
    )
    register_tools(server)
    _SERVER = server
    logger.info("MCP server initialized")
    return server


def get_server() -> FastMCP:
    """Return the singleton MCP server instance."""
    return create_server()


def main() -> None:
    """Run the MCP server over stdio transport."""
    server = create_server()
    server.run(transport="stdio")
