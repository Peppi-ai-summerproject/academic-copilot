from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from app.mcp.registry import register_tools
from app.mcp.tools.curriculum import get_curriculum
from app.mcp.tools.events import get_upcoming_events
from app.mcp.tools.health import ping
from app.mcp.tools.progress import get_progress
from app.mcp.tools.report import generate_report
from app.mcp.tools.search_students import search_students
from app.mcp.tools.student import get_student, get_student_by_number
from app.mcp.tools.courses import get_course, search_courses
from app.mcp.tools.teachers import get_teacher, search_teachers
from app.mcp.tools.enrollments import get_course_roster, get_enrollment, get_student_enrollments
from app.mcp.tools.teacher_assignments import get_course_teachers, get_teacher_courses
from app.mcp.tools.student_dashboard import get_student_dashboard
from app.mcp.tools.study_right import get_study_right
from app.mcp.tools.results import get_course_results, get_student_results, get_course_completion_analytics
from app.mcp.tools.student_groups import (
    search_student_groups,
    get_student_group,
    get_student_group_students,
    get_student_group_courses,
)


EXPECTED_HANDLERS = {
    "ping": ping,
    "get_student": get_student,
    "get_progress": get_progress,
    "generate_report": generate_report,
    "get_study_right": get_study_right,
    "get_curriculum": get_curriculum,
    "get_upcoming_events": get_upcoming_events,
    "search_students": search_students,
    "get_student_dashboard": get_student_dashboard,
    "get_student_by_number": get_student_by_number,
    "get_course": get_course,
    "search_courses": search_courses,
    "get_teacher": get_teacher,
    "search_teachers": search_teachers,
    "get_course_roster": get_course_roster,
    "get_student_enrollments": get_student_enrollments,
    "get_enrollment": get_enrollment,
    "get_course_teachers": get_course_teachers,
    "get_teacher_courses": get_teacher_courses,
    "get_course_results": get_course_results,
    "get_student_results": get_student_results,
    "get_course_completion_analytics": get_course_completion_analytics,
    "search_student_groups": search_student_groups,
    "get_student_group": get_student_group,
    "get_student_group_students": get_student_group_students,
    "get_student_group_courses": get_student_group_courses,
}

EXPECTED_INPUT_CONTRACTS = {
    "ping": ({}, set()),
    "get_student": ({"student_id": ("integer", None)}, {"student_id"}),
    "get_progress": ({"student_id": ("integer", None)}, {"student_id"}),
    "generate_report": (
        {
            "student_id": ("integer", None),
            "report_type": ("string", "academic_summary"),
        },
        {"student_id"},
    ),
    "get_study_right": ({"student_id": ("integer", None)}, {"student_id"}),
    "get_curriculum": ({"programme": ("string", None)}, {"programme"}),
    "get_upcoming_events": (
        {"start_date": (None, None), "end_date": (None, None)},
        set(),
    ),
    "search_students": (
        {
            "query": (None, None),
            "programme_code": (None, None),
            "group_name": (None, None),
            "limit": ("integer", 20),
            "offset": ("integer", 0),
        },
        set(),
    ),
    "get_student_dashboard": (
        {"student_id": ("integer", None)},
        {"student_id"},
    ),
    "get_student_by_number": ({"student_number": ("string", None)}, {"student_number"}),
    "get_course": (
        {"course_id": (None, None), "course_code": (None, None)},
        set(),
    ),
    "search_courses": (
        {"query": (None, None), "limit": ("integer", 20), "offset": ("integer", 0)},
        set(),
    ),
    "get_teacher": ({"teacher_id": ("integer", None)}, {"teacher_id"}),
    "search_teachers": (
        {"query": (None, None), "limit": ("integer", 20), "offset": ("integer", 0)},
        set(),
    ),
    "get_course_roster": (
        {"course_id": ("integer", None), "enrollment_status": (None, None)},
        {"course_id"},
    ),
    "get_student_enrollments": (
        {"student_id": ("integer", None), "enrollment_status": (None, None)},
        {"student_id"},
    ),
    "get_enrollment": (
        {"student_id": ("integer", None), "course_id": ("integer", None)},
        {"student_id", "course_id"},
    ),
    "get_course_teachers": (
        {
            "course_id": (None, None),
            "course_code": (None, None),
            "role": (None, None),
        },
        set(),
    ),
    "get_teacher_courses": (
        {"teacher_id": ("integer", None), "role": (None, None)},
        {"teacher_id"},
    ),
    "get_course_results": ({"course_code": ("string", None), "status": (None, None)}, {"course_code"}),
    "get_student_results": ({"student_id": ("integer", None), "status": (None, None)}, {"student_id"}),
    "get_course_completion_analytics": ({"course_code": ("string", None)}, {"course_code"}),
    "search_student_groups": ({"query": (None, None)}, set()),
    "get_student_group": ({"group_id": ("integer", None)}, {"group_id"}),
    "get_student_group_students": ({"group_id": ("integer", None)}, {"group_id"}),
    "get_student_group_courses": ({"group_id": ("integer", None)}, {"group_id"}),
}


def fresh_server() -> FastMCP:
    server = FastMCP(name="mcp-contract-tests")
    register_tools(server)
    return server


def test_registry_inventory_and_handlers_match_production_contract() -> None:
    server = fresh_server()
    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == set(EXPECTED_HANDLERS)
    for name, handler in EXPECTED_HANDLERS.items():
        assert server._tool_manager.get_tool(name).fn is handler


def test_registered_input_schemas_match_public_contract() -> None:
    tools = asyncio.run(fresh_server().list_tools())

    for tool in tools:
        expected_properties, expected_required = EXPECTED_INPUT_CONTRACTS[tool.name]
        properties = tool.inputSchema.get("properties", {})
        actual_properties = {
            name: (schema.get("type"), schema.get("default"))
            for name, schema in properties.items()
        }

        assert actual_properties == expected_properties
        assert set(tool.inputSchema.get("required", [])) == expected_required
        assert json.loads(json.dumps(tool.inputSchema)) == tool.inputSchema


def test_unknown_tool_is_not_registered() -> None:
    assert fresh_server()._tool_manager.get_tool("find_students_at_risk") is None
