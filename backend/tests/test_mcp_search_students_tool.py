"""Unit tests for search_students MCP tool — Issue #76."""

from unittest.mock import Mock, patch

from app.mcp.tools.search_students import search_students


def _make_success_response(students=None, total=None):
    students = students or []
    total = total if total is not None else len(students)
    return {
        "success": True,
        "query": {"text": None, "programme_code": None,
                  "group_name": None, "limit": 20, "offset": 0},
        "pagination": {"limit": 20, "offset": 0,
                       "returned": len(students), "total": total,
                       "has_more": False},
        "students": students,
    }


@patch("app.mcp.tools.search_students.SessionLocal")
def test_search_students_returns_success_response(session_local_mock: Mock) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    student_row = {
        "id": 1,
        "student_number": "S001",
        "name": "Mikael Virtanen",
        "group_name": "TT21A",
        "programme": "Business IT",
        "start_date": "2021-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    count_result = Mock()
    count_result.scalar.return_value = 1
    rows_result = Mock()
    rows_result.mappings.return_value.all.return_value = [student_row]
    database_session.execute.side_effect = [count_result, rows_result]

    result = search_students(query="mikael")

    assert result["success"] is True
    assert len(result["students"]) == 1
    assert result["students"][0]["name"] == "Mikael Virtanen"
    database_session.close.assert_called_once()


@patch("app.mcp.tools.search_students.SessionLocal")
def test_search_students_returns_empty_list_on_no_match(session_local_mock: Mock) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    count_result = Mock()
    count_result.scalar.return_value = 0
    rows_result = Mock()
    rows_result.mappings.return_value.all.return_value = []
    database_session.execute.side_effect = [count_result, rows_result]

    result = search_students(query="zzz_nonexistent")

    assert result["success"] is True
    assert result["students"] == []
    assert result["pagination"]["total"] == 0
    database_session.close.assert_called_once()


@patch("app.mcp.tools.search_students.SessionLocal")
def test_search_students_handles_database_error(session_local_mock: Mock) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session
    database_session.execute.side_effect = RuntimeError("DB connection lost")

    result = search_students(query="anna")

    assert result["success"] is False
    assert result["error"] == "DATABASE_ERROR"
    assert "search" in result["message"].lower()
    database_session.close.assert_called_once()


@patch("app.mcp.tools.search_students.SessionLocal")
def test_session_closes_on_success(session_local_mock: Mock) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    count_result = Mock()
    count_result.scalar.return_value = 0
    rows_result = Mock()
    rows_result.mappings.return_value.all.return_value = []
    database_session.execute.side_effect = [count_result, rows_result]

    search_students()

    database_session.close.assert_called_once()


@patch("app.mcp.tools.search_students.SessionLocal")
def test_session_closes_on_error(session_local_mock: Mock) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session
    database_session.execute.side_effect = Exception("Unexpected error")

    search_students()

    database_session.close.assert_called_once()


@patch("app.mcp.tools.search_students.SessionLocal")
def test_search_students_passes_filters_to_service(session_local_mock: Mock) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    count_result = Mock()
    count_result.scalar.return_value = 0
    rows_result = Mock()
    rows_result.mappings.return_value.all.return_value = []
    database_session.execute.side_effect = [count_result, rows_result]

    result = search_students(
        query="anna",
        programme_code="DIN2024S",
        group_name="TT21A",
        limit=10,
        offset=5,
    )

    assert result["success"] is True
    assert result["query"]["text"] == "anna"
    assert result["query"]["programme_code"] == "DIN2024S"
    assert result["query"]["group_name"] == "TT21A"


@patch("app.mcp.tools.search_students.SessionLocal")
def test_search_students_invalid_limit_returns_error(session_local_mock: Mock) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    result = search_students(limit=0)

    assert result["success"] is False
    assert result["error"] == "INVALID_SEARCH_PARAMETERS"
    database_session.close.assert_called_once()
