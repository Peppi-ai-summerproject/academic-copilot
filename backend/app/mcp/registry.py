from mcp.server.fastmcp import FastMCP

from app.mcp.tools.health import ping
from app.mcp.tools.progress import get_progress
from app.mcp.tools.report import generate_report
from app.mcp.tools.student import get_student, get_student_by_number
from app.mcp.tools.courses import get_course, search_courses
from app.mcp.tools.teachers import get_teacher, search_teachers
from app.mcp.tools.study_right import get_study_right
from app.mcp.tools.curriculum import get_curriculum
from app.mcp.tools.events import get_upcoming_events
from app.mcp.tools.search_students import search_students
from app.mcp.tools.student_dashboard import get_student_dashboard
from app.mcp.tools.results import get_course_results, get_student_results, get_course_completion_analytics


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
    server.add_tool(get_student_by_number, name="get_student_by_number", description="Retrieve a student profile using an exact student number.")
    server.add_tool(get_course, name="get_course", description="Retrieve a course by its numeric ID or exact course code.")
    server.add_tool(search_courses, name="search_courses", description="Search course names and codes, or list available courses.")
    server.add_tool(get_teacher, name="get_teacher", description="Retrieve a teacher directory record by numeric ID.")
    server.add_tool(search_teachers, name="search_teachers", description="Search teacher names or list the teacher directory.")
    server.add_tool(get_course_results, name="get_course_results", description="Return enrolled students' course results, including unfinished records.")
    server.add_tool(get_student_results, name="get_student_results", description="Return a student's course results and unfinished enrollments.")
    server.add_tool(get_course_completion_analytics, name="get_course_completion_analytics", description="Calculate enrollment-based pass, failure, and completion analytics for a course.")

    server.add_tool(
        get_progress,
        name="get_progress",
        description=(
            "Calculate a student's completed ECTS, compare it with the "
            "curriculum expectation, and return an academic progress summary."
        ),
    )

    server.add_tool(
        generate_report,
        name="generate_report",
        description=(
            "Generate a structured academic report for a student by "
            "combining profile, progress, study-right, curriculum, and "
            "upcoming event information."
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

    server.add_tool(
        search_students,
        name="search_students",
        description=(
            "Search student profiles using partial identity information "
            "and optional academic filters."
        ),
    )

    server.add_tool(
        get_student_dashboard,
        name="get_student_dashboard",
        description=(
            "Return a complete student overview including profile, academic "
            "progress, study right status, risk information, and upcoming "
            "academic or tutor actions."
        ),
    )

