"""Unit tests for AgentState and create_initial_state — Issue #87."""

import pytest

from app.agents.state import AgentState, create_initial_state
from app.agents.types import AgentResult, WorkflowStatus


def test_initial_state_preserves_user_message():
    state = create_initial_state(user_message="How is student S001?")

    assert state.user_message == "How is student S001?"


def test_initial_state_auto_generates_request_id():
    state = create_initial_state(user_message="test")

    assert state.request_id
    assert len(state.request_id) > 0


def test_initial_state_uses_provided_request_id():
    state = create_initial_state(
        user_message="test",
        request_id="req-123",
    )

    assert state.request_id == "req-123"


def test_initial_state_preserves_student_id():
    state = create_initial_state(
        user_message="test",
        student_id=42,
    )

    assert state.student_id == 42


def test_initial_state_student_id_defaults_to_none():
    state = create_initial_state(user_message="test")

    assert state.student_id is None


def test_initial_state_conversation_id_defaults_to_none():
    state = create_initial_state(user_message="test")

    assert state.conversation_id is None


def test_initial_state_telegram_fields_default_to_none():
    state = create_initial_state(user_message="test")

    assert state.telegram_user_id is None
    assert state.telegram_chat_id is None


def test_initial_state_collections_start_empty():
    state = create_initial_state(user_message="test")

    assert state.selected_agents == []
    assert state.pending_agents == []
    assert state.completed_agents == []
    assert state.agent_results == {}
    assert state.warnings == []
    assert state.errors == []


def test_initial_state_step_count_starts_at_zero():
    state = create_initial_state(user_message="test")

    assert state.step_count == 0


def test_initial_state_workflow_status_is_pending():
    state = create_initial_state(user_message="test")

    assert state.workflow_status == WorkflowStatus.PENDING


def test_initial_state_current_agent_is_none():
    state = create_initial_state(user_message="test")

    assert state.current_agent is None


def test_initial_state_final_response_is_none():
    state = create_initial_state(user_message="test")

    assert state.final_response is None


def test_initial_state_max_steps_default():
    state = create_initial_state(user_message="test")

    assert state.max_steps == 10


def test_initial_state_custom_max_steps():
    state = create_initial_state(
        user_message="test",
        max_steps=5,
    )

    assert state.max_steps == 5


def test_separate_states_do_not_share_warnings():
    state1 = create_initial_state(user_message="request 1")
    state2 = create_initial_state(user_message="request 2")

    state1.warnings.append("warning")

    assert state1.warnings == ["warning"]
    assert state2.warnings == []


def test_separate_states_do_not_share_agent_results():
    state1 = create_initial_state(user_message="request 1")
    state2 = create_initial_state(user_message="request 2")

    result = AgentResult(
        agent_name="progress",
        route="progress",
        status="SUCCESS",
        summary="Progress analysis completed.",
    )

    state1.agent_results["progress"] = result

    assert state1.agent_results["progress"] == result
    assert "progress" not in state2.agent_results


def test_empty_user_message_raises_error():
    with pytest.raises(ValueError, match="user_message must not be empty"):
        create_initial_state(user_message="")


def test_whitespace_user_message_raises_error():
    with pytest.raises(ValueError, match="user_message must not be empty"):
        create_initial_state(user_message="   ")


def test_empty_request_id_raises_error():
    with pytest.raises(ValueError, match="request_id must not be empty"):
        AgentState(
            request_id="",
            user_message="valid message",
        )


def test_whitespace_request_id_raises_error():
    with pytest.raises(ValueError, match="request_id must not be empty"):
        AgentState(
            request_id="   ",
            user_message="valid message",
        )


def test_is_step_limit_reached_false_at_start():
    state = create_initial_state(
        user_message="test",
        max_steps=10,
    )

    assert state.is_step_limit_reached() is False


def test_is_step_limit_reached_true_when_at_limit():
    state = create_initial_state(
        user_message="test",
        max_steps=3,
    )
    state.step_count = 3

    assert state.is_step_limit_reached() is True


def test_is_step_limit_reached_true_when_above_limit():
    state = create_initial_state(
        user_message="test",
        max_steps=3,
    )
    state.step_count = 4

    assert state.is_step_limit_reached() is True


def test_get_agent_result_returns_none_when_not_present():
    state = create_initial_state(user_message="test")

    assert state.get_agent_result("progress") is None


def test_get_agent_result_returns_result_when_present():
    state = create_initial_state(user_message="test")

    result = AgentResult(
        agent_name="progress",
        route="progress",
        status="SUCCESS",
        summary="Progress analysis completed.",
    )

    state.agent_results["progress"] = result

    assert state.get_agent_result("progress") == result


def test_has_errors_false_when_no_errors():
    state = create_initial_state(user_message="test")

    assert state.has_errors() is False


def test_has_errors_true_when_errors_present():
    state = create_initial_state(user_message="test")
    state.errors.append("something went wrong")

    assert state.has_errors() is True


def test_max_steps_must_be_at_least_one():
    with pytest.raises(ValueError):
        create_initial_state(
            user_message="test",
            max_steps=0,
        )


def test_step_count_cannot_be_negative():
    with pytest.raises(ValueError):
        AgentState(
            request_id="req-123",
            user_message="valid message",
            step_count=-1,
        )


def test_state_handles_multiple_selected_and_pending_agents():
    state = create_initial_state(user_message="Analyze student progress")

    state.selected_agents = ["progress", "risk", "recommendation"]
    state.pending_agents = ["risk", "recommendation"]
    state.current_agent = "progress"

    assert state.selected_agents == ["progress", "risk", "recommendation"]
    assert state.pending_agents == ["risk", "recommendation"]
    assert state.current_agent == "progress"