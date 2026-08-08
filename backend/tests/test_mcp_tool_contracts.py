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
from app.mcp.tools.student import get_student
from app.mcp.tools.student_dashboard import get_student_dashboard
from app.mcp.tools.study_right import get_study_right


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
