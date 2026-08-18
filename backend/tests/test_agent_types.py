"""Unit tests for AgentResult and related types — Issue #87."""

from typing import get_args

import pytest

from app.agents.types import (
    AgentName,
    AgentResult,
    AgentStatus,
    EvidenceItem,
    WorkflowStatus,
)


def test_agent_name_values_are_strings():
    for name in AgentName:
        assert isinstance(name.value, str)


def test_agent_name_has_expected_members():
    assert {name.value for name in AgentName} == {
        "progress",
        "study_rights",
        "risk",
        "calendar",
        "recommendation",
        "communication",
        "reporting",
        "academic_data",
    }


def test_agent_status_has_expected_values():
    assert set(get_args(AgentStatus)) == {
        "SUCCESS",
        "PARTIAL",
        "FAILED",
        "SKIPPED",
    }


def test_workflow_status_has_expected_values():
    assert WorkflowStatus.PENDING.value == "pending"
    assert WorkflowStatus.RUNNING.value == "running"
    assert WorkflowStatus.COMPLETED.value == "completed"
    assert WorkflowStatus.PARTIAL.value == "partial"
    assert WorkflowStatus.FAILED.value == "failed"


def test_evidence_item_can_be_created():
    evidence = EvidenceItem(
        source="database",
        tool_name="get_progress",
        data={"ects": 60},
    )

    assert evidence.source == "database"
    assert evidence.tool_name == "get_progress"
    assert evidence.data["ects"] == 60


def test_evidence_item_defaults_are_safe():
    evidence = EvidenceItem(source="mcp")

    assert evidence.tool_name == ""
    assert evidence.reference == ""
    assert evidence.description == ""
    assert evidence.data == {}


def test_separate_evidence_items_do_not_share_data():
    first = EvidenceItem(source="database")
    second = EvidenceItem(source="mcp")

    assert first.data is not second.data


def test_agent_result_successful_creation():
    result = AgentResult(
        agent_name="progress",
        route="progress",
        status="SUCCESS",
        summary="On track.",
        data={"completed_ects": 120},
    )

    assert result.agent_name == "progress"
    assert result.route == "progress"
    assert result.status == "SUCCESS"
    assert result.summary == "On track."
    assert result.data["completed_ects"] == 120


def test_agent_result_partial_with_warnings():
    result = AgentResult(
        agent_name="study_rights",
        route="study_rights",
        status="PARTIAL",
        summary="Some information is unavailable.",
        warnings=["Curriculum missing."],
    )

    assert result.status == "PARTIAL"
    assert result.warnings == ["Curriculum missing."]


def test_agent_result_failed_with_errors():
    result = AgentResult(
        agent_name="risk",
        route="risk",
        status="FAILED",
        summary="Risk analysis failed.",
        errors=["DB timeout."],
    )

    assert result.status == "FAILED"
    assert result.errors == ["DB timeout."]


def test_agent_result_skipped_creation():
    result = AgentResult(
        agent_name="calendar",
        route="calendar",
        status="SKIPPED",
        summary="Calendar analysis was not required.",
    )

    assert result.status == "SKIPPED"


def test_agent_result_defaults_are_safe():
    result = AgentResult(
        agent_name="calendar",
        route="calendar",
        status="SUCCESS",
        summary="",
    )

    assert result.data == {}
    assert result.evidence == []
    assert result.warnings == []
    assert result.errors == []


def test_separate_agent_results_do_not_share_mutable_defaults():
    first = AgentResult(
        agent_name="progress",
        route="progress",
        status="SUCCESS",
        summary="First result.",
    )
    second = AgentResult(
        agent_name="risk",
        route="risk",
        status="SUCCESS",
        summary="Second result.",
    )

    first.warnings.append("warning")

    assert second.warnings == []
    assert first.data is not second.data
    assert first.evidence is not second.evidence
    assert first.warnings is not second.warnings
    assert first.errors is not second.errors


def test_invalid_status_raises_error():
    with pytest.raises(ValueError, match="Invalid agent status"):
        AgentResult(
            agent_name="progress",
            route="progress",
            status="invalid_status",
            summary="Invalid result.",
        )


def test_invalid_route_raises_error():
    with pytest.raises(ValueError, match="Invalid agent route"):
        AgentResult(
            agent_name="progress",
            route="invalid_route",
            status="SUCCESS",
            summary="Invalid result.",
        )


def test_agent_result_with_evidence():
    result = AgentResult(
        agent_name="progress",
        route="progress",
        status="SUCCESS",
        summary="Progress retrieved.",
        evidence=["get_progress:student-42"],
    )

    assert result.evidence == ["get_progress:student-42"]


def test_finish_route_is_valid():
    result = AgentResult(
        agent_name="supervisor",
        route="finish",
        status="SUCCESS",
        summary="Workflow completed.",
    )

    assert result.route == "finish"
