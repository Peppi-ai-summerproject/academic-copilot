from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SQLAlchemyError

from app.mcp.tools.events import get_upcoming_events


@patch("app.mcp.tools.events.SessionLocal")
@patch("app.mcp.tools.events.EventRepository")
@patch("app.mcp.tools.events.EventService")
def test_get_upcoming_events_success(
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

    service.get_upcoming_events.return_value = {
        "success": True,
        "filters": {
            "start_date": "2026-01-01",
            "end_date": None,
        },
        "event_count": 1,
        "events": [],
    }

    result = get_upcoming_events(
        start_date="2026-01-01",
    )

    assert result["success"] is True

    service.get_upcoming_events.assert_called_once_with(
        start_date="2026-01-01",
        end_date=None,
    )

    session.close.assert_called_once()


@patch("app.mcp.tools.events.SessionLocal")
@patch("app.mcp.tools.events.EventRepository")
@patch("app.mcp.tools.events.EventService")
def test_get_upcoming_events_returns_validation_error(
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

    service.get_upcoming_events.return_value = {
        "success": False,
        "error": "INVALID_START_DATE",
        "message": "Start date must use YYYY-MM-DD format.",
    }

    result = get_upcoming_events(
        start_date="01-01-2026",
    )

    assert result["success"] is False
    assert result["error"] == "INVALID_START_DATE"
    session.close.assert_called_once()


@patch("app.mcp.tools.events.SessionLocal")
def test_get_upcoming_events_database_error(
    mock_session_local,
) -> None:
    session = MagicMock()
    mock_session_local.return_value = session

    with patch(
        "app.mcp.tools.events.EventRepository",
        side_effect=SQLAlchemyError(),
    ):
        result = get_upcoming_events(
            start_date="2026-01-01",
        )

    assert result == {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Failed to retrieve upcoming events.",
    }

    session.close.assert_called_once()