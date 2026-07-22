from mcp.server.fastmcp import FastMCP

from app.mcp.tools.health import ping
from app.mcp.tools.progress import get_progress
from app.mcp.tools.student import get_student
from app.mcp.tools.study_right import get_study_right
from app.mcp.tools.curriculum import get_curriculum
from app.mcp.tools.events import get_upcoming_events


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

    server.add_tool(
        get_progress,
        name="get_progress",
        description=(
            "Calculate a student's completed ECTS, compare it with the "
            "curriculum expectation, and return an academic progress summary."
        ),
    )

    server.add_tool(
        get_study_right,
        name="get_study_right",
        description=(
            "Retrieve a student's study right status, expiration date, "
            "and whether the study right is expiring soon."
        ),
    )

    server.add_tool(
        get_curriculum,
        name="get_curriculum",
        description=(
            "Retrieve curriculum requirements for a programme, "
            "including expected ECTS for each semester."
        ),
    )


    server.add_tool(
        get_upcoming_events,
        name="get_upcoming_events",
        description=(
            "Retrieve upcoming tutoring activities and academic events, "
            "optionally filtered by start and end dates."
        ),
    )