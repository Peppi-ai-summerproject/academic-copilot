from app.agents.base import AgentResult
from app.agents.state import (
    AgentStateValidationError,
    create_initial_state,
    validate_agent_state,
)
from app.agents.types import AgentRoute


def test_create_initial_state_defaults_and_fields() -> None:
    state = create_initial_state(
        request_id="req-1",
        intent="student progress",
        route="progress",
        user_message="Show me the student's progress.",
        student_id=123,
    )

    assert state.request_id == "req-1"
    assert state.intent == "student progress"
    assert state.route == "progress"
    assert state.user_message == "Show me the student's progress."
    assert state.student_id == 123
    assert state.selected_agents == ["progress"]
    assert state.pending_agents == ["progress"]
    assert state.completed_agents == []
    assert state.step_count == 0
    assert state.max_steps == 10
    assert state.workflow_status == "PENDING"
    assert state.agent_outputs == {}
    assert state.warnings == []
    assert state.errors == []
    assert state.final_response is None


def test_initial_state_uses_separate_mutable_collections() -> None:
    first = create_initial_state(
        request_id="req-2",
        intent="risk",
        route="risk",
    )
    second = create_initial_state(
        request_id="req-3",
        intent="risk",
        route="risk",
    )

    assert first.parameters is not second.parameters
    assert first.selected_agents is not second.selected_agents
    assert first.warnings is not second.warnings
    assert first.errors is not second.errors


def test_validate_agent_state_rejects_invalid_request_id() -> None:
    try:
        create_initial_state(
            request_id="",
            intent="progress",
            route="progress",
        )
    except AgentStateValidationError as error:
        assert "request_id must not be empty" in error.message
    else:
        raise AssertionError("Expected AgentStateValidationError")


def test_validate_agent_state_rejects_step_count_exceeding_max() -> None:
    state = create_initial_state(
        request_id="req-4",
        intent="calendar",
        route="calendar",
    )
    state.step_count = 11

    try:
        validate_agent_state(state)
    except AgentStateValidationError as error:
        assert "step_count cannot exceed max_steps" in error.message
    else:
        raise AssertionError("Expected AgentStateValidationError")


def test_state_handles_multiple_selected_agents() -> None:
    state = create_initial_state(
        request_id="req-5",
        intent="report",
        route="reporting",
        selected_agents=["reporting", "communication"],
    )

    assert state.selected_agents == ["reporting", "communication"]
    assert state.pending_agents == ["reporting", "communication"]
    assert state.current_agent is None
    assert state.next_agent is None
    assert state.workflow_status == "PENDING"
