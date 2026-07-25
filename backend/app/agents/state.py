from __future__ import annotations

from typing import Any, get_args

from app.agents.types import AgentRoute, AgentState, WorkflowStatus
from app.core.exceptions import AppException


class AgentStateValidationError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, status_code=400, error_code="INVALID_AGENT_STATE")


def create_initial_state(
    *,
    request_id: str,
    intent: str,
    route: AgentRoute,
    user_message: str | None = None,
    conversation_id: str | None = None,
    telegram_user_id: str | None = None,
    telegram_chat_id: str | None = None,
    student_id: int | None = None,
    parameters: dict[str, Any] | None = None,
    selected_agents: list[AgentRoute] | None = None,
    max_steps: int = 10,
) -> AgentState:
    if not request_id:
        raise AgentStateValidationError("request_id must not be empty.")

    if not intent:
        raise AgentStateValidationError("intent must not be empty.")

    if max_steps <= 0:
        raise AgentStateValidationError("max_steps must be a positive integer.")

    active_agents = selected_agents if selected_agents is not None else [route]

    state = AgentState(
        request_id=request_id,
        intent=intent,
        route=route,
        student_id=student_id,
        user_message=user_message,
        conversation_id=conversation_id,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
        parameters=parameters or {},
        selected_agents=list(active_agents),
        pending_agents=list(active_agents),
        completed_agents=[],
        current_agent=None,
        next_agent=None,
        step_count=0,
        max_steps=max_steps,
        agent_outputs={},
        warnings=[],
        errors=[],
        final_response=None,
        response_format=None,
        workflow_status="PENDING",
        metadata={},
    )

    validate_agent_state(state)
    return state


def validate_agent_state(state: AgentState) -> None:
    if not state.request_id:
        raise AgentStateValidationError("request_id must not be empty.")

    if not state.intent:
        raise AgentStateValidationError("intent must not be empty.")

    if state.step_count < 0:
        raise AgentStateValidationError("step_count must be non-negative.")

    if state.max_steps <= 0:
        raise AgentStateValidationError("max_steps must be a positive integer.")

    if state.step_count > state.max_steps:
        raise AgentStateValidationError("step_count cannot exceed max_steps.")

    if state.current_agent is not None and state.current_agent not in state.selected_agents:
        raise AgentStateValidationError("current_agent must be one of the selected_agents or None.")

    if state.next_agent is not None and state.next_agent not in state.selected_agents:
        raise AgentStateValidationError("next_agent must be one of the selected_agents or None.")

    valid_workflow_statuses = get_args(WorkflowStatus)
    if state.workflow_status not in valid_workflow_statuses:
        raise AgentStateValidationError(
            "workflow_status must be one of: "
            + ", ".join(valid_workflow_statuses),
        )

    valid_agent_routes = get_args(AgentRoute)

    if state.current_agent is not None and state.current_agent not in valid_agent_routes:
        raise AgentStateValidationError("current_agent must be a valid AgentRoute.")

    if state.next_agent is not None and state.next_agent not in valid_agent_routes:
        raise AgentStateValidationError("next_agent must be a valid AgentRoute.")

    for agent_name in [*state.selected_agents, *state.pending_agents, *state.completed_agents]:
        if agent_name not in valid_agent_routes:
            raise AgentStateValidationError(f"Invalid agent name: {agent_name}")

    for agent_name in state.agent_outputs.keys():
        if agent_name not in valid_agent_routes:
            raise AgentStateValidationError(f"Invalid agent output key: {agent_name}")
