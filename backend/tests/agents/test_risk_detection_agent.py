from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents.risk_detection_agent import RiskDetectionAgent
from app.agents.state import create_initial_state
from app.agents.workflow import create_academic_agent_workflow, create_default_agent_registry
from app.services.risk_policy import DEADLINE_EVENT_TYPES


TODAY = date(2026, 8, 3)


def student(success: bool = True) -> dict[str, Any]:
    if not success:
        return {"success": False, "error": "STUDENT_NOT_FOUND"}
    return {
        "success": True,
        "student": {"id": 42, "name": "Ada Student", "programme": "Computer Science"},
    }


def progress(
    status: str = "ON_TRACK", completed: int = 120, expected: int = 120
) -> dict[str, Any]:
    return {
        "success": True,
        "progress": {
            "status": status,
            "completed_ects": completed,
            "expected_ects": expected,
            "difference_ects": completed - expected,
        },
    }


def study_right(status: str = "ACTIVE") -> dict[str, Any]:
    return {
        "success": True,
        "study_right": {
            "status": status,
            "expiration_date": "2028-07-31",
            "extension_count": 0,
        },
    }


def event(
    days: int,
    *,
    event_type: str = "DEADLINE",
    global_event: bool = True,
) -> dict[str, Any]:
    return {
        "id": 7,
        "event_name": "Course registration deadline",
        "event_type": event_type,
        "event_date": (TODAY + timedelta(days=days)).isoformat(),
        "affects_all_students": global_event,
    }


def gateway(
    *,
    student_result: dict[str, Any] | None = None,
    progress_result: dict[str, Any] | None = None,
    study_right_result: dict[str, Any] | None = None,
    event_result: dict[str, Any] | None = None,
) -> Mock:
    result = Mock()
    result.get_student = AsyncMock(return_value=student_result or student())
    result.get_progress = AsyncMock(return_value=progress_result or progress())
    result.get_study_right = AsyncMock(return_value=study_right_result or study_right())
    result.get_upcoming_events = AsyncMock(
        return_value=event_result or {"success": True, "events": []}
    )
    return result


def run(agent: RiskDetectionAgent, student_id: int | None = 42):
    state = create_initial_state(user_message="Assess risk", student_id=student_id)
    return asyncio.run(agent.run(state))


def agent(fake_gateway: Mock) -> RiskDetectionAgent:
    return RiskDetectionAgent(fake_gateway, date_provider=lambda: TODAY)


def test_complete_assessment_with_no_factors_returns_none():
    result = run(agent(gateway()))

    assert result.status == "SUCCESS"
    assert result.data["risk_level"] == "NONE"
    assert result.data["risk_factors"] == []
    assert result.data["assessment_complete"] is True
    assert "no confirmed academic risk" in result.summary.lower()


@pytest.mark.parametrize(
    ("completed", "expected", "level"),
    [(119, 120, "LOW"), (90, 120, "MEDIUM"), (60, 120, "HIGH")],
)
def test_progress_thresholds_reuse_project_policy(completed, expected, level):
    result = run(
        agent(gateway(progress_result=progress("BEHIND", completed, expected)))
    )

    factor = result.data["risk_factors"][0]
    assert result.data["risk_level"] == level
    assert factor["dimension"] == "progress"
    assert factor["values"] == {
        "completed_ects": completed,
        "expected_ects": expected,
        "ects_deficit": expected - completed,
    }
    assert "ECTS behind" in factor["reason"]


@pytest.mark.parametrize(
    ("status", "level", "reason_text"),
    [
        ("EXPIRED", "HIGH", "expired"),
        ("EXPIRES_SOON", "MEDIUM", "expiring soon"),
        ("EXTENDED", "MEDIUM", "extended"),
    ],
)
def test_study_right_risk_levels_and_explanations(status, level, reason_text):
    result = run(agent(gateway(study_right_result=study_right(status))))

    factor = result.data["risk_factors"][0]
    assert result.data["risk_level"] == level
    assert factor["dimension"] == "study_right"
    assert factor["values"]["status"] == status
    assert reason_text in factor["reason"].lower()


@pytest.mark.parametrize(("days", "expected"), [(0, "MEDIUM"), (14, "MEDIUM"), (15, "NONE")])
def test_deadline_window_boundaries(days, expected):
    result = run(
        agent(gateway(event_result={"success": True, "events": [event(days)]}))
    )

    assert result.data["risk_level"] == expected
    if expected == "MEDIUM":
        factor = result.data["risk_factors"][0]
        assert factor["values"]["days_until_event"] == days
        assert factor["values"]["globally_applicable"] is True
        assert "Global academic deadline" in factor["reason"]


def test_non_deadline_and_non_global_events_do_not_create_risk():
    events = [event(2, event_type="REGISTRATION"), event(2, global_event=False)]
    result = run(agent(gateway(event_result={"success": True, "events": events})))

    assert DEADLINE_EVENT_TYPES == frozenset({"DEADLINE"})
    assert result.data["risk_level"] == "NONE"
    assert "missed" not in result.summary.lower()


def test_multiple_factors_are_retained_and_highest_level_wins():
    fake = gateway(
        progress_result=progress("BEHIND", 50, 120),
        event_result={"success": True, "events": [event(1)]},
    )
    result = run(agent(fake))

    assert result.data["risk_level"] == "HIGH"
    assert [factor["dimension"] for factor in result.data["risk_factors"]] == [
        "progress", "academic_event"
    ]
    assert len(result.evidence) == 2
    assert "70 ECTS" in result.summary
    assert "deadline" in result.summary.lower()


@pytest.mark.parametrize(
    ("dimension", "changes"),
    [
        ("progress", {"progress_result": {"success": False, "error": "UNAVAILABLE"}}),
        ("study_right", {"study_right_result": {"success": False, "error": "UNAVAILABLE"}}),
        ("academic_events", {"event_result": {"success": False, "error": "UNAVAILABLE"}}),
    ],
)
def test_unavailable_dimension_makes_assessment_partial(dimension, changes):
    result = run(agent(gateway(**changes)))

    assert result.status == "PARTIAL"
    assert result.data["risk_level"] == "NONE"
    assert result.data["assessment_complete"] is False
    assert dimension in result.data["unavailable_dimensions"]
    assert "inconclusive" in result.summary.lower()
    assert "no confirmed academic risk factors" not in result.summary.lower()


def test_partial_high_assessment_remains_high_and_retains_factor():
    fake = gateway(
        progress_result=progress("BEHIND", 30, 120),
        event_result={"success": False, "error": "EVENTS_UNAVAILABLE"},
    )
    result = run(agent(fake))

    assert result.status == "PARTIAL"
    assert result.data["risk_level"] == "HIGH"
    assert result.data["risk_factors"][0]["dimension"] == "progress"
    assert result.summary.startswith("Partial assessment:")


def test_malformed_dimension_is_partial_not_safe():
    result = run(agent(gateway(progress_result={"success": True, "progress": {}})))

    assert result.status == "PARTIAL"
    assert result.data["risk_level"] == "NONE"
    assert "progress" in result.data["unavailable_dimensions"]


def test_non_dictionary_dependency_response_is_treated_as_unavailable():
    fake = gateway()
    fake.get_progress.return_value = None
    result = run(agent(fake))

    assert result.status == "PARTIAL"
    assert "progress" in result.data["unavailable_dimensions"]


def test_missing_student_id_and_missing_student_are_controlled():
    fake = gateway()
    missing_id = run(agent(fake), None)
    missing_student = run(agent(gateway(student_result=student(False))))

    assert missing_id.status == "FAILED"
    fake.get_student.assert_not_awaited()
    assert missing_student.status == "FAILED"
    assert "not found" in missing_student.summary.lower()


def test_all_dimensions_are_attempted_and_dependency_details_are_not_exposed():
    fake = gateway(progress_result=progress("BEHIND", 20, 120))
    secret = "postgresql://admin:password@internal-db:5432"
    fake.get_study_right.side_effect = RuntimeError(secret)
    result = run(agent(fake))

    fake.get_progress.assert_awaited_once_with(42)
    fake.get_study_right.assert_awaited_once_with(42)
    fake.get_upcoming_events.assert_awaited_once_with()
    assert result.status == "PARTIAL"
    assert result.data["risk_level"] == "HIGH"
    assert secret not in repr(result)
    assert "internal-db" not in repr(result)


def test_student_gateway_exception_returns_safe_failure():
    fake = gateway()
    fake.get_student.side_effect = RuntimeError("Supabase secret endpoint")
    result = run(agent(fake))

    assert result.status == "FAILED"
    assert result.summary == "Risk assessment could not be completed due to a system error."
    assert "Supabase" not in repr(result)


def test_production_registry_contains_real_risk_agent():
    registry = create_default_agent_registry()
    assert registry.get("risk") is RiskDetectionAgent


def test_workflow_executes_real_risk_agent():
    fake = gateway()
    workflow = create_academic_agent_workflow(gateway=fake)
    state = create_initial_state(user_message="Assess risk", student_id=42)
    state.selected_agents = ["risk"]

    result = asyncio.run(workflow.run(state))

    assert result.agent_results["risk"].agent_name == "RiskDetectionAgent"
    assert result.agent_results["risk"].data["risk_level"] == "NONE"
    assert result.completed_agents == ["risk"]
