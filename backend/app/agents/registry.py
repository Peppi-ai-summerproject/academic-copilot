from __future__ import annotations

from typing import Dict, Type

from app.agents.base import AcademicAgent
from app.agents.types import AgentRoute
from app.gateways.academic_tools import AcademicToolGateway
from app.gateways.policy_context import PolicyContextGateway


class AgentRegistry:
    """A lightweight registry for future academic agent implementations."""

    def __init__(self) -> None:
        self._agents: Dict[AgentRoute, Type[AcademicAgent]] = {}

    def register(self, route: AgentRoute, agent: Type[AcademicAgent]) -> None:
        self._agents[route] = agent

    def get(self, route: AgentRoute) -> Type[AcademicAgent] | None:
        return self._agents.get(route)

    def routes(self) -> list[AgentRoute]:
        return list(self._agents.keys())

    def all(self) -> Dict[AgentRoute, Type[AcademicAgent]]:
        return dict(self._agents)

    def create(
        self,
        route: AgentRoute,
        *,
        academic_gateway: AcademicToolGateway,
        policy_gateway: PolicyContextGateway,
    ) -> AcademicAgent | None:
        agent_type = self.get(route)
        if agent_type is None:
            return None
        if route in {"reporting", "communication"}:
            return agent_type()
        if route == "recommendation":
            return agent_type(academic_gateway, policy_gateway)
        return agent_type(academic_gateway)
