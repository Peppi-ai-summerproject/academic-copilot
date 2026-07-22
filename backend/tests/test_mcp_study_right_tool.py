from datetime import date
from unittest.mock import Mock, patch

from app.mcp.tools.study_right import get_study_right


@patch("app.mcp.tools.study_right.SessionLocal")
def test_get_study_right_tool_returns_record(
    session_local_mock: Mock,
) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    database_session.execute.return_value.mappings.return_value.first.return_value = {
        "id": 1,
        "student_id": 1,
        "start_date": date(2021, 9, 1),
        "end_date": date(2027, 5, 31),
        "status": "ACTIVE",
        "extension_count": 0,
    }

    result = get_study_right(1)

    assert result["success"] is True
    assert result["study_right"]["status"] == "ACTIVE"
    assert result["study_right"]["expiration_date"] == date(2027, 5, 31)
    assert result["study_right"]["is_expiring_soon"] is False

    database_session.close.assert_called_once()


@patch("app.mcp.tools.study_right.SessionLocal")
def test_get_study_right_tool_detects_expiring_status(
    session_local_mock: Mock,
) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    database_session.execute.return_value.mappings.return_value.first.return_value = {
        "id": 2,
        "student_id": 2,
        "start_date": date(2021, 9, 1),
        "end_date": date(2025, 7, 31),
        "status": "EXPIRES_SOON",
        "extension_count": 1,
    }

    result = get_study_right(2)

    assert result["success"] is True
    assert result["study_right"]["is_expiring_soon"] is True

    database_session.close.assert_called_once()


@patch("app.mcp.tools.study_right.SessionLocal")
def test_get_study_right_tool_handles_missing_record(
    session_local_mock: Mock,
) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session

    database_session.execute.return_value.mappings.return_value.first.return_value = None

    result = get_study_right(999)

    assert result["success"] is False
    assert result["error"] == "STUDY_RIGHT_NOT_FOUND"

    database_session.close.assert_called_once()


@patch("app.mcp.tools.study_right.SessionLocal")
def test_get_study_right_tool_handles_database_error(
    session_local_mock: Mock,
) -> None:
    database_session = Mock()
    session_local_mock.return_value = database_session
    database_session.execute.side_effect = RuntimeError("Database unavailable")

    result = get_study_right(1)

    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Study right information could not be retrieved.",
    }

    database_session.close.assert_called_once()