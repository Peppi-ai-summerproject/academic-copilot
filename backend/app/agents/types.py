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


@dataclass
class AgentState:
    request_id: str
    intent: str
    route: AgentRoute
    student_id: int | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
