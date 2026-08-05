import asyncio
from unittest.mock import MagicMock, patch

from app.agents.calendar_agent import CalendarAgent
from app.agents.state import AgentState


@patch("app.agents.calendar_agent.CalendarAgent._get_upcoming_events")
def test_calendar_agent_returns_upcoming_events(mock_get) -> None:
    mock_get.return_value = {
        "success": True,
        "filters": {
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        "event_count": 1,
        "events": [
            {
                "id": 1,
                "event_name": "Tutor Meeting",
                "event_type": "Meeting",
                "event_date": "2026-09-15",
                "end_date": None,
                "academic_year": "2026-2027",
                "semester": 1,
                "description": "Weekly tutoring session.",
                "affects_all_students": False,
            }
        ],
    }

    agent = CalendarAgent()
    state = AgentState(
        request_id="req-123",
        user_message="Show upcoming tutoring events.",
        intent="upcoming tutoring events",
        student_id=42,
        parameters={
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
    )

    result = asyncio.run(agent.run(state))

    assert result.status == "SUCCESS"
    assert result.data["event_count"] == 1
    assert result.data["events"][0]["title"] == "Tutor Meeting"
    mock_get.assert_called_once_with(
        start_date="2026-09-01",
        end_date="2026-09-30",
    )


@patch("app.agents.calendar_agent.CalendarAgent._get_upcoming_events")
def test_calendar_agent_returns_no_events(mock_get) -> None:
    mock_get.return_value = {
        "success": True,
        "filters": {
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        "event_count": 0,
        "events": [],
    }

    agent = CalendarAgent()
    state = AgentState(
        request_id="req-456",
        user_message="Show the calendar overview.",
        intent="calendar overview",
        parameters={"start_date": "2026-09-01"},
    )

    result = asyncio.run(agent.run(state))

    assert result.status == "SUCCESS"
    assert result.data["event_count"] == 0
    assert result.data["events"] == []
    assert "No upcoming calendar events" in result.summary


def test_calendar_agent_handles_invalid_student_id() -> None:
    agent = CalendarAgent()
    state = AgentState(
        request_id="req-789",
        user_message="Show the calendar.",
        intent="calendar query",
        student_id=0,
        parameters={"start_date": "2026-09-01"},
    )

    result = asyncio.run(agent.run(state))

    assert result.status == "FAILED"
    assert "INVALID_STUDENT_ID" in result.errors
    assert result.data["student_id"] == 0


@patch("app.agents.calendar_agent.CalendarAgent._get_upcoming_events")
def test_calendar_agent_handles_tool_failure(mock_get) -> None:
    mock_get.return_value = {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Failed to retrieve upcoming events.",
    }

    agent = CalendarAgent()
    state = AgentState(
        request_id="req-321",
        user_message="Show the calendar.",
        intent="calendar query",
        parameters={"start_date": "2026-09-01"},
    )

    result = asyncio.run(agent.run(state))

    assert result.status == "FAILED"
    assert "DATABASE_ERROR" in result.errors
    assert result.data["requested_dates"]["start_date"] == "2026-09-01"
