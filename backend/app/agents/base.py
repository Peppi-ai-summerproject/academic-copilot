from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.agents.types import AgentRoute, AgentState, AgentStatus


@dataclass
class AgentResult:
    agent_name: str
    route: AgentRoute
    status: AgentStatus
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class AcademicAgent(Protocol):
    name: str
    description: str

    async def run(self, state: AgentState) -> AgentResult:
        ...
