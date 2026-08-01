"""Unit tests for AgentResult and types — Issue #87."""

import pytest
from app.agents.types import AgentName, AgentResult, AgentStatus, EvidenceItem, WorkflowStatus


def test_agent_name_values_are_strings():
    for name in AgentName:
        assert isinstance(name.value, str)

def test_agent_name_has_expected_members():
    names = {n.value for n in AgentName}
    for expected in ["progress", "study_rights", "risk", "calendar", "recommendation", "communication", "reporting"]:
        assert expected in names

def test_agent_status_has_expected_values():
    assert AgentStatus.SUCCESS.value == "success"
    assert AgentStatus.PARTIAL.value == "partial"
    assert AgentStatus.FAILED.value == "failed"
    assert AgentStatus.SKIPPED.value == "skipped"

def test_workflow_status_has_expected_values():
    assert WorkflowStatus.PENDING.value == "pending"
    assert WorkflowStatus.RUNNING.value == "running"
    assert WorkflowStatus.COMPLETED.value == "completed"
    assert WorkflowStatus.PARTIAL.value == "partial"
    assert WorkflowStatus.FAILED.value == "failed"

def test_evidence_item_can_be_created():
    e = EvidenceItem(source="database", tool_name="get_progress", data={"ects": 60})
    assert e.source == "database"
    assert e.data["ects"] == 60

def test_evidence_item_defaults_are_safe():
    e = EvidenceItem(source="mcp")
    assert e.tool_name == ""
    assert e.data == {}

def test_agent_result_successful_creation():
    result = AgentResult(agent_name="progress", status=AgentStatus.SUCCESS,
                         summary="On track.", data={"completed_ects": 120})
    assert result.agent_name == "progress"
    assert result.status == AgentStatus.SUCCESS
    assert result.data["completed_ects"] == 120

def test_agent_result_partial_with_warnings():
    result = AgentResult(agent_name="study_rights", status=AgentStatus.PARTIAL,
                         warnings=["Curriculum missing."])
    assert result.has_warnings() is True

def test_agent_result_failed_with_errors():
    result = AgentResult(agent_name="risk", status=AgentStatus.FAILED,
                         errors=["DB timeout."])
    assert result.has_errors() is True
    assert result.is_successful() is False

def test_agent_result_is_successful_for_success():
    assert AgentResult(agent_name="p", status=AgentStatus.SUCCESS).is_successful() is True

def test_agent_result_is_successful_for_partial():
    assert AgentResult(agent_name="p", status=AgentStatus.PARTIAL).is_successful() is True

def test_agent_result_is_not_successful_for_failed():
    assert AgentResult(agent_name="p", status=AgentStatus.FAILED).is_successful() is False

def test_agent_result_is_not_successful_for_skipped():
    assert AgentResult(agent_name="p", status=AgentStatus.SKIPPED).is_successful() is False

def test_agent_result_defaults_are_safe():
    result = AgentResult(agent_name="calendar", status=AgentStatus.SUCCESS)
    assert result.summary == ""
    assert result.data == {}
    assert result.evidence == []
    assert result.warnings == []
    assert result.errors == []

def test_invalid_status_raises_error():
    with pytest.raises(Exception):
        AgentResult(agent_name="progress", status="invalid_status")

def test_agent_result_with_evidence():
    evidence = EvidenceItem(source="mcp_tool", tool_name="get_progress")
    result = AgentResult(agent_name="progress", status=AgentStatus.SUCCESS, evidence=[evidence])
    assert len(result.evidence) == 1
    assert result.evidence[0].source == "mcp_tool"
