from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SQLAlchemyError

from app.mcp.tools.curriculum import get_curriculum


@patch("app.mcp.tools.curriculum.SessionLocal")
@patch("app.mcp.tools.curriculum.CurriculumRepository")
@patch("app.mcp.tools.curriculum.CurriculumService")
def test_get_curriculum_success(
    mock_service_class,
    mock_repository_class,
    mock_session_local,
) -> None:
    session = MagicMock()
    mock_session_local.return_value = session

    repository = MagicMock()
    mock_repository_class.return_value = repository

    service = MagicMock()
    mock_service_class.return_value = service

    service.get_curriculum.return_value = {
        "success": True,
        "curriculum": {
            "programme": "Business IT",
            "semesters": [],
            "total_expected_ects": 240,
        },
    }

    result = get_curriculum("Business IT")

    assert result["success"] is True
    service.get_curriculum.assert_called_once_with("Business IT")
    session.close.assert_called_once()


@patch("app.mcp.tools.curriculum.SessionLocal")
@patch("app.mcp.tools.curriculum.CurriculumRepository")
@patch("app.mcp.tools.curriculum.CurriculumService")
def test_get_curriculum_not_found(
    mock_service_class,
    mock_repository_class,
    mock_session_local,
) -> None:
    session = MagicMock()
    mock_session_local.return_value = session

    repository = MagicMock()
    mock_repository_class.return_value = repository

    service = MagicMock()
    mock_service_class.return_value = service

    service.get_curriculum.return_value = {
        "success": False,
        "error": "CURRICULUM_NOT_FOUND",
    }

    result = get_curriculum("Unknown")

    assert result["error"] == "CURRICULUM_NOT_FOUND"
    session.close.assert_called_once()


@patch("app.mcp.tools.curriculum.SessionLocal")
def test_get_curriculum_database_error(
    mock_session_local,
) -> None:
    session = MagicMock()
    mock_session_local.return_value = session

    with patch(
        "app.mcp.tools.curriculum.CurriculumRepository",
        side_effect=SQLAlchemyError(),
    ):
        result = get_curriculum("Business IT")

    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Failed to retrieve curriculum information.",
    }

    session.close.assert_called_once()