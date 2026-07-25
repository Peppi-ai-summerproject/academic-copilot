from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AgentRoute = Literal[
    "calendar",
    "progress",
    "study_rights",
    "risk",
    "recommendation",
    "reporting",
    "communication",
    "finish",
]

AgentStatus = Literal["SUCCESS", "WARNING", "FAILED", "PARTIAL", "UNKNOWN"]
WorkflowStatus = Literal["PENDING", "RUNNING", "COMPLETED", "PARTIAL", "FAILED"]


@dataclass
class AgentState:
    request_id: str
    intent: str
    route: AgentRoute
    student_id: int | None = None
    conversation_id: str | None = None
    user_message: str | None = None
    telegram_user_id: str | None = None
    telegram_chat_id: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    selected_agents: list[AgentRoute] = field(default_factory=list)
    pending_agents: list[AgentRoute] = field(default_factory=list)
    completed_agents: list[AgentRoute] = field(default_factory=list)
    current_agent: AgentRoute | None = None
    next_agent: AgentRoute | None = None
    step_count: int = 0
    max_steps: int = 10
    agent_outputs: dict[AgentRoute, "AgentResult"] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    final_response: dict[str, Any] | None = None
    response_format: str | None = None
    workflow_status: WorkflowStatus = "PENDING"
    metadata: dict[str, Any] = field(default_factory=dict)
