from __future__ import annotations

import asyncio

from app.agents.registry import AgentRegistry
from app.agents.reporting_agent import ReportingAgent
from app.agents.state import AgentState, create_initial_state
from app.agents.types import AgentResult, WorkflowStatus
from app.agents.workflow import AcademicAgentWorkflow


class FakeGateway:
    pass


def agent_type(route: str, status: str = "SUCCESS", order: list[str] | None = None):
    class FakeAgent:
        def __init__(self, gateway) -> None:
            self.gateway = gateway

        async def run(self, state: AgentState) -> AgentResult:
            if order is not None:
                order.append(route)
            return AgentResult(
                agent_name=f"{route.title()}Agent",
                route=route,
                status=status,
                summary=f"{route} finished",
                warnings=[f"{route} warning"] if status == "PARTIAL" else [],
                errors=[f"{route} failed"] if status == "FAILED" else [],
            )

    return FakeAgent


class ExplodingAgent:
    def __init__(self, gateway) -> None:
        pass

    async def run(self, state: AgentState) -> AgentResult:
        raise RuntimeError("boom")


def make_workflow(*registrations: tuple[str, type]) -> AcademicAgentWorkflow:
    registry = AgentRegistry()
    for route, agent in registrations:
        registry.register(route, agent)
    return AcademicAgentWorkflow(registry, FakeGateway())


def run(workflow: AcademicAgentWorkflow, state: AgentState) -> AgentState:
    return asyncio.run(workflow.run(state))


def test_empty_selection_completes_without_execution():
    result = run(make_workflow(), create_initial_state(user_message="hello"))

    assert result.workflow_status is WorkflowStatus.COMPLETED
    assert result.step_count == 0
    assert result.agent_results == {}


def test_single_agent_success_accumulates_result_and_tracking():
    state = create_initial_state(user_message="progress", student_id=1)
    state.selected_agents = ["progress"]

    result = run(make_workflow(("progress", agent_type("progress"))), state)

    assert result.workflow_status is WorkflowStatus.COMPLETED
    assert result.completed_agents == ["progress"]
    assert result.pending_agents == []
    assert result.step_count == 1
    assert result.agent_results["progress"].summary == "progress finished"


def test_multiple_agents_execute_in_selected_order():
    order: list[str] = []
    state = create_initial_state(user_message="analyse", student_id=1)
    state.selected_agents = ["study_rights", "progress"]
    workflow = make_workflow(
        ("progress", agent_type("progress", order=order)),
        ("study_rights", agent_type("study_rights", order=order)),
    )

    result = run(workflow, state)

    assert order == ["study_rights", "progress"]
    assert result.completed_agents == order
    assert set(result.agent_results) == {"study_rights", "progress"}
    assert result.workflow_status is WorkflowStatus.COMPLETED


def test_partial_agent_makes_workflow_partial_and_collects_warning():
    state = create_initial_state(user_message="progress")
    state.selected_agents = ["progress"]

    result = run(
        make_workflow(("progress", agent_type("progress", "PARTIAL"))), state
    )

    assert result.workflow_status is WorkflowStatus.PARTIAL
    assert result.warnings == ["progress warning"]


def test_failed_result_makes_workflow_failed_and_preserves_result():
    state = create_initial_state(user_message="progress")
    state.selected_agents = ["progress"]

    result = run(
        make_workflow(("progress", agent_type("progress", "FAILED"))), state
    )

    assert result.workflow_status is WorkflowStatus.FAILED
    assert result.agent_results["progress"].status == "FAILED"
    assert result.errors == ["progress failed"]


def test_agent_exception_is_recorded_without_crashing_workflow():
    state = create_initial_state(user_message="progress")
    state.selected_agents = ["progress"]

    result = run(make_workflow(("progress", ExplodingAgent)), state)

    assert result.workflow_status is WorkflowStatus.FAILED
    assert result.completed_agents == ["progress"]
    assert "boom" in result.errors[0]


def test_unknown_agent_is_handled_safely():
    state = create_initial_state(user_message="calendar")
    state.selected_agents = ["calendar"]

    result = run(make_workflow(), state)

    assert result.workflow_status is WorkflowStatus.FAILED
    assert result.completed_agents == ["calendar"]
    assert "No registered agent" in result.errors[0]


def test_success_plus_failure_produces_partial_status():
    state = create_initial_state(user_message="analyse")
    state.selected_agents = ["progress", "study_rights"]
    workflow = make_workflow(
        ("progress", agent_type("progress")),
        ("study_rights", agent_type("study_rights", "FAILED")),
    )

    result = run(workflow, state)

    assert result.workflow_status is WorkflowStatus.PARTIAL
    assert result.step_count == 2


def test_max_steps_stops_execution_and_marks_workflow_failed():
    state = create_initial_state(user_message="analyse", max_steps=1)
    state.selected_agents = ["progress", "study_rights"]
    workflow = make_workflow(
        ("progress", agent_type("progress")),
        ("study_rights", agent_type("study_rights")),
    )

    result = run(workflow, state)

    assert result.step_count == 1
    assert result.completed_agents == ["progress"]
    assert result.pending_agents == ["study_rights"]
    assert result.workflow_status is WorkflowStatus.PARTIAL


def test_duplicate_routes_execute_only_once():
    state = create_initial_state(user_message="progress")
    state.selected_agents = ["progress", "progress"]

    result = run(make_workflow(("progress", agent_type("progress"))), state)

    assert result.selected_agents == ["progress"]
    assert result.step_count == 1


def test_communication_result_sets_final_response_through_workflow_state():
    class CommunicationAgent:
        def __init__(self) -> None:
            pass

        async def run(self, state: AgentState) -> AgentResult:
            return AgentResult(
                agent_name="CommunicationAgent",
                route="communication",
                status="SUCCESS",
                summary="Response formatted.",
                data={"formatted_message": "Tutor-ready response"},
            )

    state = create_initial_state(user_message="format")
    state.selected_agents = ["communication"]
    result = run(make_workflow(("communication", CommunicationAgent)), state)

    assert result.final_response == "Tutor-ready response"
    assert result.workflow_status is WorkflowStatus.COMPLETED


def test_reporting_before_upstream_agents_is_partial_and_does_not_set_final_response():
    state = create_initial_state(user_message="report", student_id=42)
    state.selected_agents = ["reporting"]

    result = run(make_workflow(("reporting", ReportingAgent)), state)

    assert result.agent_results["reporting"].status == "PARTIAL"
    assert result.agent_results["reporting"].data["overall_status"] == "unavailable"
    assert result.final_response is None
    assert result.workflow_status is WorkflowStatus.PARTIAL
