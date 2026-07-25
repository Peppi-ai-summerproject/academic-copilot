from unittest.mock import MagicMock, patch

from app.mcp.tools.progress import get_progress


@patch("app.mcp.tools.progress.SessionLocal")
@patch("app.mcp.tools.progress.ProgressService")
@patch("app.mcp.tools.progress.ProgressRepository")
def test_get_progress_tool_returns_progress(
    mock_repository_class: MagicMock,
    mock_service_class: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    session = MagicMock()
    repository = MagicMock()
    service = MagicMock()

    mock_session_local.return_value = session
    mock_repository_class.return_value = repository
    mock_service_class.return_value = service

    service.get_progress.return_value = {
        "success": True,
        "progress": {
            "student_id": 1,
            "programme": "Business IT",
            "current_semester": 4,
            "completed_ects": 90,
            "expected_ects": 120,
            "difference_ects": -30,
            "remaining_to_expected_ects": 30,
            "progress_percentage": 75.0,
            "status": "BEHIND",
        },
    }

    result = get_progress(1)

    assert result["success"] is True
    assert result["progress"]["student_id"] == 1
    assert result["progress"]["status"] == "BEHIND"

    mock_repository_class.assert_called_once_with(session)
    mock_service_class.assert_called_once_with(repository)
    service.get_progress.assert_called_once_with(1)
    session.close.assert_called_once()


@patch("app.mcp.tools.progress.SessionLocal")
@patch("app.mcp.tools.progress.ProgressService")
@patch("app.mcp.tools.progress.ProgressRepository")
def test_get_progress_tool_handles_missing_student(
    mock_repository_class: MagicMock,
    mock_service_class: MagicMock,
    mock_session_local: MagicMock,
) -> None:
    session = MagicMock()
    repository = MagicMock()
    service = MagicMock()

    mock_session_local.return_value = session
    mock_repository_class.return_value = repository
    mock_service_class.return_value = service

    service.get_progress.return_value = {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 999 was not found.",
    }

    result = get_progress(999)

    assert result == {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 999 was not found.",
    }

    service.get_progress.assert_called_once_with(999)
    session.close.assert_called_once()


@patch("app.mcp.tools.progress.SessionLocal")
def test_get_progress_tool_handles_database_error(
    mock_session_local: MagicMock,
) -> None:
    session = MagicMock()
    mock_session_local.return_value = session

    with patch(
        "app.mcp.tools.progress.ProgressRepository",
        side_effect=Exception("Database connection failed"),
    ):
        result = get_progress(1)

    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Academic progress could not be retrieved.",
    }

    session.close.assert_called_once()