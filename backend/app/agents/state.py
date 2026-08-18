"""Shared Agent State for the multi-agent workflow — Issue #87."""

from __future__ import annotations
import uuid
from typing import Any
from pydantic import BaseModel, Field, field_validator
from app.agents.types import WorkflowStatus
from app.schemas.memory import ConversationMemorySnapshot


class AgentState(BaseModel):
    """Shared execution state for one multi-agent workflow run.

    Created once at workflow entry. Updated via partial node returns.
    Not persisted — lives only for the duration of one workflow execution.
    Do NOT store DB sessions, MCP clients, or API keys here.
    """

    # Request context
    request_id: str = Field(description="Unique identifier for this workflow execution.")
    conversation_id: str | None = Field(default=None)
    user_message: str = Field(description="Original message from the tutor teacher.")
    telegram_user_id: int | None = Field(default=None)
    telegram_chat_id: int | None = Field(default=None)
    memory: ConversationMemorySnapshot | None = Field(default=None)

    # Academic context
    student_id: int | None = Field(default=None)
    student_name: str | None = Field(default=None)
    programme: str | None = Field(default=None)
    resolved_entities: list[dict[str, Any]] = Field(default_factory=list)

    # Routing context (managed by Supervisor/Router — Issue #79)
    intent: str | None = Field(default=None)
    parameters: dict[str, Any] = Field(default_factory=dict)
    selected_agents: list[str] = Field(default_factory=list)
    pending_agents: list[str] = Field(default_factory=list)
    completed_agents: list[str] = Field(default_factory=list)
    current_agent: str | None = Field(default=None)
    step_count: int = Field(default=0, ge=0)
    max_steps: int = Field(default=10, ge=1)

    # Collaboration context
    agent_results: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # Output context
    final_response: str | None = Field(default=None)
    workflow_status: WorkflowStatus = Field(default=WorkflowStatus.PENDING)

    model_config = {"frozen": False}

    @field_validator("request_id")
    @classmethod
    def request_id_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("request_id must not be empty.")
        return value

    @field_validator("user_message")
    @classmethod
    def user_message_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("user_message must not be empty.")
        return value

    def is_step_limit_reached(self) -> bool:
        return self.step_count >= self.max_steps

    def get_agent_result(self, agent_name: str) -> Any | None:
        return self.agent_results.get(agent_name)

    def has_errors(self) -> bool:
        return len(self.errors) > 0


def create_initial_state(
    *,
    user_message: str,
    request_id: str | None = None,
    student_id: int | None = None,
    conversation_id: str | None = None,
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
    memory: ConversationMemorySnapshot | None = None,
    max_steps: int = 10,
    parameters: dict[str, Any] | None = None,
) -> AgentState:
    """Create a fresh initial AgentState for a new workflow execution."""
    return AgentState(
        request_id=request_id or str(uuid.uuid4()),
        conversation_id=conversation_id,
        user_message=user_message,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
        memory=memory,
        student_id=student_id,
        student_name=None,
        programme=None,
        resolved_entities=[],
        intent=None,
        parameters=parameters or {},
        selected_agents=[],
        pending_agents=[],
        completed_agents=[],
        current_agent=None,
        step_count=0,
        max_steps=max_steps,
        agent_results={},
        warnings=[],
        errors=[],
        final_response=None,
        workflow_status=WorkflowStatus.PENDING,
    )
