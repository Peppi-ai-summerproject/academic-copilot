from __future__ import annotations

from app.core.logger import logger


def ping() -> dict[str, str]:
    """Health check tool for the MCP server."""
    logger.info("MCP ping tool called")
    return {
        "status": "ok",
        "service": "academic-copilot-mcp",
    }
