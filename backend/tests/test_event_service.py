from datetime import date
from unittest.mock import MagicMock

from app.services.event_service import EventService


def test_get_upcoming_events_returns_event_details() -> None:
    repository = MagicMock()
    repository.get_upcoming_events.return_value = [
        {
            "id": 1,
            "event_name": "Mid-year progress review",
            "event_type": "CHECK_IN",
            "event_date": date(2026, 1, 15),
            "end_date": None,
            "academic_year": "2025-2026",
            "semester": 2,
            "description": "Progress review for all students",
            "affects_all_students": True,
        }
    ]

    service = EventService(repository)

    result = service.get_upcoming_events(
        start_date="2026-01-01",
    )

    assert result == {
        "success": True,
        "filters": {
            "start_date": "2026-01-01",
            "end_date": None,
        },
        "event_count": 1,
        "events": [
            {
                "id": 1,
                "event_name": "Mid-year progress review",
                "event_type": "CHECK_IN",
                "event_date": "2026-01-15",
                "end_date": None,
                "academic_year": "2025-2026",
                "semester": 2,
                "description": "Progress review for all students",
                "affects_all_students": True,
            }
        ],
    }

    repository.get_upcoming_events.assert_called_once_with(
        start_date=date(2026, 1, 1),
        end_date=None,
    )


def test_get_upcoming_events_supports_date_range() -> None:
    repository = MagicMock()
    repository.get_upcoming_events.return_value = []

    service = EventService(repository)

    result = service.get_upcoming_events(
        start_date="2026-01-01",
        end_date="2026-01-31",
    )

    assert result["success"] is True
    assert result["filters"] == {
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
    }

    repository.get_upcoming_events.assert_called_once_with(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )


def test_get_upcoming_events_returns_empty_list() -> None:
    repository = MagicMock()
    repository.get_upcoming_events.return_value = []

    service = EventService(repository)

    result = service.get_upcoming_events(
        start_date="2026-01-01",
    )

    assert result["success"] is True
    assert result["event_count"] == 0
    assert result["events"] == []


def test_get_upcoming_events_returns_invalid_start_date_error() -> None:
    repository = MagicMock()
    service = EventService(repository)

    result = service.get_upcoming_events(
        start_date="01-01-2026",
    )

    assert result == {
        "success": False,
        "error": "INVALID_START_DATE",
        "message": "Start date must use YYYY-MM-DD format.",
    }

    repository.get_upcoming_events.assert_not_called()


def test_get_upcoming_events_returns_invalid_end_date_error() -> None:
    repository = MagicMock()
    service = EventService(repository)

    result = service.get_upcoming_events(
        start_date="2026-01-01",
        end_date="31-01-2026",
    )

    assert result == {
        "success": False,
        "error": "INVALID_END_DATE",
        "message": "End date must use YYYY-MM-DD format.",
    }

    repository.get_upcoming_events.assert_not_called()


def test_get_upcoming_events_returns_invalid_date_range_error() -> None:
    repository = MagicMock()
    service = EventService(repository)

    result = service.get_upcoming_events(
        start_date="2026-02-01",
        end_date="2026-01-01",
    )

    assert result == {
        "success": False,
        "error": "INVALID_DATE_RANGE",
        "message": "End date must not be before start date.",
    }

    repository.get_upcoming_events.assert_not_called()