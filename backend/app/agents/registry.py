from __future__ import annotations

from typing import Dict, Type

from app.agents.base import AcademicAgent
from app.agents.types import AgentRoute


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
