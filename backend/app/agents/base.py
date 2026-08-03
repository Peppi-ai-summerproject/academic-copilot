from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

from app.agents.types import AgentResult

if TYPE_CHECKING:
    from app.agents.state import AgentState


class AcademicAgent(Protocol):
    """Contract implemented by every academic agent."""

    name: str
    description: str

    async def run(self, state: AgentState) -> AgentResult:
        ...
