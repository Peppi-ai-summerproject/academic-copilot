"""
MCP Integration Tests — Issue #75

Validates the complete MCP tool ecosystem:
- Tool registration
- Tool execution
- Response structure
- Error handling
- Registry consistency

Uses the real FastMCP server and registry (no MagicMock for registration).
Follows the patterns established in test_mcp_server.py and test_mcp_demo.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch, Mock

import pytest
from mcp.server.fastmcp import FastMCP

from app.mcp.registry import register_tools
from app.mcp.server import create_server

# ── Expected registered tools (from actual registry inspection) ───────────────
EXPECTED_TOOLS = {
    "ping",
    "get_student",
    "get_progress",
    "get_study_right",
    "get_curriculum",
    "get_upcoming_events",
    "search_students",
    "generate_report",
    "get_student_dashboard",
    "get_student_by_number",
    "get_course",
    "search_courses",
    "get_teacher",
    "search_teachers",
    "get_course_results",
    "get_student_results",
    "get_course_completion_analytics",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def fresh_server() -> FastMCP:
    """Create a fresh FastMCP server with all tools registered.

    Uses a new instance to avoid singleton state pollution between tests.
    """
    server = FastMCP(name="integration-test-server")
    register_tools(server)
    return server


def list_tools(server: FastMCP) -> list:
    return asyncio.run(server.list_tools())


def tool_names(server: FastMCP) -> set[str]:
    return {tool.name for tool in list_tools(server)}


# ── 1. Tool Registration Tests ────────────────────────────────────────────────

def test_all_expected_tools_are_registered() -> None:
    """Every expected tool must appear in the registry."""
    server = fresh_server()
    names = tool_names(server)
    for expected in EXPECTED_TOOLS:
        assert expected in names, f"Tool '{expected}' is not registered"


def test_no_unexpected_tools_are_registered() -> None:
    """Registry must not silently add tools not in EXPECTED_TOOLS."""
    server = fresh_server()
    names = tool_names(server)
    unexpected = names - EXPECTED_TOOLS
    assert not unexpected, f"Unexpected tools registered: {unexpected}"


def test_no_duplicate_tool_registrations() -> None:
    """Each tool name must appear exactly once."""
    server = fresh_server()
    all_tools = list_tools(server)
    names = [tool.name for tool in all_tools]
    assert len(names) == len(set(names)), f"Duplicate tools found: {names}"


def test_tool_count_matches_expected() -> None:
    """Number of registered tools must equal expected count."""
    server = fresh_server()
    assert len(tool_names(server)) == len(EXPECTED_TOOLS)


def test_every_tool_has_a_description() -> None:
    """Every registered tool must have a non-empty description."""
    server = fresh_server()
    for tool in list_tools(server):
        assert tool.description, f"Tool '{tool.name}' has no description"
        assert len(tool.description.strip()) > 0


# ── 2. Description Content Tests ─────────────────────────────────────────────

def test_ping_description() -> None:
    server = fresh_server()
    tools = {t.name: t for t in list_tools(server)}
    assert "health" in tools["ping"].description.lower() or            "check" in tools["ping"].description.lower()


def test_get_student_description_mentions_student() -> None:
    server = fresh_server()
    tools = {t.name: t for t in list_tools(server)}
    desc = tools["get_student"].description.lower()
    assert "student" in desc


def test_get_progress_description_mentions_ects() -> None:
    server = fresh_server()
    tools = {t.name: t for t in list_tools(server)}
    desc = tools["get_progress"].description.lower()
    assert "ects" in desc or "progress" in desc


def test_search_students_description_mentions_search_and_student() -> None:
    server = fresh_server()
    tools = {t.name: t for t in list_tools(server)}
    desc = tools["search_students"].description.lower()
    assert "search" in desc
    assert "student" in desc


# ── 3. Tool Execution — ping (no DB needed) ───────────────────────────────────

def test_ping_tool_executes_successfully() -> None:
    """ping requires no database and must always succeed."""
    server = fresh_server()
    tool = server._tool_manager.get_tool("ping")
    result = tool.fn()
    assert isinstance(result, dict)
    assert result.get("status") == "ok"
    assert result.get("service") == "academic-copilot-mcp"


def test_ping_returns_dict() -> None:
    server = fresh_server()
    tool = server._tool_manager.get_tool("ping")
    result = tool.fn()
    assert isinstance(result, dict)


# ── 4. Tool Execution — DB tools with mocked session ─────────────────────────

def _make_db_mock(rows=None, first=None, scalar=None):
    """Helper: build a Mock session that returns controlled query results."""
    session = Mock()
    if first is not None:
        session.execute.return_value.mappings.return_value.first.return_value = first
    if rows is not None:
        session.execute.return_value.mappings.return_value.all.return_value = rows
    if scalar is not None:
        session.execute.return_value.scalar.return_value = scalar
    return session


def test_get_student_returns_success_for_existing_student() -> None:
    student_row = {
        "id": 1, "student_number": "S001", "name": "Mikael Virtanen",
        "group_name": "TT21A", "programme": "Business IT",
        "start_date": "2021-09-01", "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.first.return_value = student_row
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_student")
        result = tool.fn(student_id=1)

    assert isinstance(result, dict)
    assert result["success"] is True
    assert "student" in result
    assert result["student"]["student_number"] == "S001"


def test_get_student_returns_error_for_missing_student() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.first.return_value = None
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_student")
        result = tool.fn(student_id=999)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result
    assert result["error"] == "STUDENT_NOT_FOUND"


def test_get_student_returns_error_for_invalid_id() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_student")
        result = tool.fn(student_id=-1)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result


def test_get_progress_returns_success_structure() -> None:
    progress_row = {
        "student_id": 1,
        "completed_ects": 60,
        "expected_ects": 90,
        "programme_code": "DIN2024S",
        "semester": 3,
    }
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.first.return_value = progress_row
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_progress")
        result = tool.fn(student_id=1)

    assert isinstance(result, dict)
    assert "success" in result


def test_get_progress_returns_error_for_missing_student() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.first.return_value = None
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_progress")
        result = tool.fn(student_id=99999)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result


def test_get_study_right_returns_success_structure() -> None:
    study_right_row = {
        "id": 1, "student_id": 1,
        "start_date": "2021-09-01", "end_date": "2028-05-31",
        "status": "ACTIVE", "extension_count": 0,
    }
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.first.return_value = study_right_row
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_study_right")
        result = tool.fn(student_id=1)

    assert isinstance(result, dict)
    assert "success" in result


def test_get_study_right_returns_error_for_missing_student() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.first.return_value = None
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_study_right")
        result = tool.fn(student_id=99999)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result


def test_get_curriculum_returns_success_structure() -> None:
    curriculum_rows = [
        {"id": 1, "programme": "Business IT", "semester": 1, "expected_ects": 30},
        {"id": 2, "programme": "Business IT", "semester": 2, "expected_ects": 60},
    ]
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.all.return_value = curriculum_rows
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_curriculum")
        result = tool.fn(programme="Business IT")

    assert isinstance(result, dict)
    assert "success" in result


def test_get_curriculum_returns_error_for_unknown_programme() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.all.return_value = []
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_curriculum")
        result = tool.fn(programme="NONEXISTENT_PROGRAMME_XYZ")

    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result


def test_get_upcoming_events_returns_success_structure() -> None:
    import datetime
    event_rows = [
        {
            "id": 1,
            "event_name": "Orientations",
            "event_type": "ORIENTATION",
            "event_date": datetime.date(2025, 9, 1),
            "end_date": None,
            "academic_year": "2025-2026",
            "semester": 1,
            "description": "New student orientations",
            "affects_all_students": True,
        }
    ]
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.all.return_value = event_rows
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_upcoming_events")
        result = tool.fn()

    assert isinstance(result, dict)
    assert "success" in result


def test_get_upcoming_events_with_date_filter() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.all.return_value = []
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_upcoming_events")
        result = tool.fn(start_date="2025-01-01", end_date="2025-12-31")

    assert isinstance(result, dict)
    assert "success" in result


def test_search_students_returns_success_structure() -> None:
    student_row = {
        "id": 1, "student_number": "S001", "name": "Mikael Virtanen",
        "group_name": "TT21A", "programme": "Business IT",
        "start_date": "2021-09-01", "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }
    with patch("app.mcp.tools.search_students.SessionLocal") as mock_sl:
        session = Mock()
        count_result = Mock()
        count_result.scalar.return_value = 1
        rows_result = Mock()
        rows_result.mappings.return_value.all.return_value = [student_row]
        session.execute.side_effect = [count_result, rows_result]
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("search_students")
        result = tool.fn(query="mikael")

    assert isinstance(result, dict)
    assert result["success"] is True
    assert "students" in result
    assert "pagination" in result


def test_search_students_empty_query_returns_paginated_results() -> None:
    with patch("app.mcp.tools.search_students.SessionLocal") as mock_sl:
        session = Mock()
        count_result = Mock()
        count_result.scalar.return_value = 0
        rows_result = Mock()
        rows_result.mappings.return_value.all.return_value = []
        session.execute.side_effect = [count_result, rows_result]
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("search_students")
        result = tool.fn()

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["students"] == []


def test_search_students_invalid_limit_returns_error() -> None:
    with patch("app.mcp.tools.search_students.SessionLocal") as mock_sl:
        session = Mock()
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("search_students")
        result = tool.fn(limit=0)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error"] == "INVALID_SEARCH_PARAMETERS"


# ── 5. Database Error Handling ────────────────────────────────────────────────

def test_get_student_handles_database_exception() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.side_effect = RuntimeError("Connection lost")
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_student")
        result = tool.fn(student_id=1)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error"] == "DATABASE_ERROR"
    assert "message" in result


def test_get_progress_handles_database_exception() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.side_effect = RuntimeError("DB error")
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_progress")
        result = tool.fn(student_id=1)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error"] == "DATABASE_ERROR"


def test_get_study_right_handles_database_exception() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.side_effect = RuntimeError("DB error")
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_study_right")
        result = tool.fn(student_id=1)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error"] == "DATABASE_ERROR"


def test_get_curriculum_handles_database_exception() -> None:
    from sqlalchemy.exc import SQLAlchemyError
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.side_effect = SQLAlchemyError("DB error")
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_curriculum")
        result = tool.fn(programme="Business IT")

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error"] == "DATABASE_ERROR"


def test_get_upcoming_events_handles_database_exception() -> None:
    from sqlalchemy.exc import SQLAlchemyError
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.side_effect = SQLAlchemyError("DB error")
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_upcoming_events")
        result = tool.fn()

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error"] == "DATABASE_ERROR"


def test_search_students_handles_database_exception() -> None:
    with patch("app.mcp.tools.search_students.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.side_effect = RuntimeError("DB error")
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("search_students")
        result = tool.fn(query="test")

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["error"] == "DATABASE_ERROR"


# ── 6. Consistency Tests ──────────────────────────────────────────────────────

def test_all_db_tools_return_dict_on_error() -> None:
    """Every DB tool must return a dict even when the database fails.

    Note: get_curriculum and get_upcoming_events only catch SQLAlchemyError,
    while other tools catch Exception. We use the appropriate exception type
    per tool to accurately test their error handling boundaries.
    """
    from sqlalchemy.exc import SQLAlchemyError

    # Tools that catch Exception (broad)
    broad_tools = [
        ("get_student", {"student_id": 1}, "app.db.database.SessionLocal"),
        ("get_progress", {"student_id": 1}, "app.db.database.SessionLocal"),
        ("get_study_right", {"student_id": 1}, "app.db.database.SessionLocal"),
        ("search_students", {"query": "test"}, "app.mcp.tools.search_students.SessionLocal"),
    ]

    # Tools that only catch SQLAlchemyError
    sqlalchemy_tools = [
        ("get_curriculum", {"programme": "Business IT"}, "app.db.database.SessionLocal"),
        ("get_upcoming_events", {}, "app.db.database.SessionLocal"),
    ]

    server = fresh_server()

    for tool_name, kwargs, target in broad_tools:
        with patch(target) as mock_sl:
            session = Mock()
            session.execute.side_effect = RuntimeError("DB failure")
            mock_sl.return_value = session
            tool = server._tool_manager.get_tool(tool_name)
            result = tool.fn(**kwargs)

        assert isinstance(result, dict), f"{tool_name} did not return dict"
        assert result["success"] is False, f"{tool_name} success should be False"
        assert "error" in result, f"{tool_name} missing error field"
        assert "message" in result, f"{tool_name} missing message field"

    for tool_name, kwargs, target in sqlalchemy_tools:
        with patch(target) as mock_sl:
            session = Mock()
            session.execute.side_effect = SQLAlchemyError("DB failure")
            mock_sl.return_value = session
            tool = server._tool_manager.get_tool(tool_name)
            result = tool.fn(**kwargs)

        assert isinstance(result, dict), f"{tool_name} did not return dict"
        assert result["success"] is False, f"{tool_name} success should be False"
        assert "error" in result, f"{tool_name} missing error field"
        assert "message" in result, f"{tool_name} missing message field"


def test_all_error_responses_use_consistent_structure() -> None:
    """All error responses must have success, error, and message fields."""
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.side_effect = RuntimeError("fail")
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_student")
        result = tool.fn(student_id=1)

    assert set(result.keys()) >= {"success", "error", "message"}
    assert result["success"] is False
    assert isinstance(result["error"], str)
    assert isinstance(result["message"], str)


# ── 7. Session Management Tests ───────────────────────────────────────────────

def test_get_student_closes_session_on_success() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.return_value.mappings.return_value.first.return_value = None
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_student")
        tool.fn(student_id=999)

    session.close.assert_called_once()


def test_get_student_closes_session_on_error() -> None:
    with patch("app.db.database.SessionLocal") as mock_sl:
        session = Mock()
        session.execute.side_effect = RuntimeError("fail")
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("get_student")
        tool.fn(student_id=1)

    session.close.assert_called_once()


def test_search_students_closes_session_on_success() -> None:
    with patch("app.mcp.tools.search_students.SessionLocal") as mock_sl:
        session = Mock()
        count_result = Mock()
        count_result.scalar.return_value = 0
        rows_result = Mock()
        rows_result.mappings.return_value.all.return_value = []
        session.execute.side_effect = [count_result, rows_result]
        mock_sl.return_value = session

        server = fresh_server()
        tool = server._tool_manager.get_tool("search_students")
        tool.fn()

    session.close.assert_called_once()


# ── 8. Registry Consistency ───────────────────────────────────────────────────

def test_registry_tool_names_are_unique() -> None:
    server = fresh_server()
    all_tools = list_tools(server)
    names = [t.name for t in all_tools]
    assert len(names) == len(set(names))


def test_create_server_returns_same_instance() -> None:
    """Singleton pattern: create_server() must return same instance."""
    server1 = create_server()
    server2 = create_server()
    assert server1 is server2


def test_fresh_server_registers_correct_tool_count() -> None:
    server = fresh_server()
    assert len(tool_names(server)) == len(EXPECTED_TOOLS)
