from datetime import date
from unittest.mock import MagicMock

from app.repositories.event_repository import EventRepository


def test_get_upcoming_events_returns_events() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.all.return_value = [
        {
            "id": 1,
            "event_name": "First-year student orientations",
            "event_type": "ORIENTATION",
            "event_date": date(2026, 8, 10),
            "end_date": None,
            "academic_year": "2026-2027",
            "semester": 1,
            "description": "Mandatory orientation for all new students",
            "affects_all_students": True,
        },
        {
            "id": 2,
            "event_name": "Course registration deadline",
            "event_type": "REGISTRATION",
            "event_date": date(2026, 8, 15),
            "end_date": None,
            "academic_year": "2026-2027",
            "semester": 1,
            "description": "Autumn registration closes",
            "affects_all_students": True,
        },
    ]

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = EventRepository(session)

    result = repository.get_upcoming_events(
        start_date=date(2026, 8, 1),
    )

    assert len(result) == 2
    assert result[0]["event_name"] == "First-year student orientations"
    assert result[1]["event_type"] == "REGISTRATION"

    parameters = session.execute.call_args.args[1]
    assert parameters == {
        "start_date": date(2026, 8, 1),
    }


def test_get_upcoming_events_supports_end_date_filter() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.all.return_value = []

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = EventRepository(session)

    result = repository.get_upcoming_events(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )

    assert result == []

    parameters = session.execute.call_args.args[1]
    assert parameters == {
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 31),
    }


def test_get_upcoming_events_returns_empty_list() -> None:
    session = MagicMock()

    mapping_result = MagicMock()
    mapping_result.all.return_value = []

    execute_result = MagicMock()
    execute_result.mappings.return_value = mapping_result
    session.execute.return_value = execute_result

    repository = EventRepository(session)

    result = repository.get_upcoming_events(
        start_date=date(2026, 8, 1),
    )

    assert result == []