from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, get_args

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

    def __post_init__(self) -> None:
        valid_route_names = get_args(AgentRoute)
        valid_statuses = get_args(AgentStatus)

        if self.route not in valid_route_names:
            raise ValueError(f"Invalid agent route: {self.route}")

        if self.status not in valid_statuses:
            raise ValueError(f"Invalid agent status: {self.status}")


class AcademicAgent(Protocol):
    name: str
    description: str

    async def run(self, state: AgentState) -> AgentResult:
        ...
