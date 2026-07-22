from unittest.mock import Mock, patch

from app.mcp.tools.student import get_student


@patch("app.mcp.tools.student.SessionLocal")
def test_get_student_tool_returns_student_profile(
    session_local_mock: Mock,
) -> None:
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

    database_session.execute.return_value.mappings.return_value.first.return_value = (
        student_row
    )

    result = get_student(1)

    assert result["success"] is True
    assert result["student"]["id"] == 1
    assert result["student"]["student_number"] == "S001"

    database_session.close.assert_called_once()


@patch("app.mcp.tools.student.SessionLocal")
def test_get_student_tool_handles_missing_record(
    session_local_mock: Mock,
) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    database_session.execute.return_value.mappings.return_value.first.return_value = None

    result = get_student(999)

    assert result["success"] is False
    assert result["error"] == "STUDENT_NOT_FOUND"

    database_session.close.assert_called_once()


@patch("app.mcp.tools.student.SessionLocal")
def test_get_student_tool_handles_database_error(
    session_local_mock: Mock,
) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session
    database_session.execute.side_effect = RuntimeError("Database unavailable")

    result = get_student(1)

    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Student information could not be retrieved.",
    }

    database_session.close.assert_called_once()