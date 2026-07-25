from __future__ import annotations

from app.agents.base import AgentResult
from app.agents.types import AgentRoute


def merge_agent_results(
    current: dict[AgentRoute, AgentResult] | None,
    update: dict[AgentRoute, AgentResult] | None,
) -> dict[AgentRoute, AgentResult]:
    if current is None:
        current = {}
    if update is None:
        update = {}

    merged = {**current, **update}
    return merged


def append_warnings(
    current: list[str] | None,
    new_warnings: list[str] | None,
) -> list[str]:
    if current is None:
        current = []
    if new_warnings is None:
        new_warnings = []

    return [*current, *new_warnings]


def append_errors(
    current: list[str] | None,
    new_errors: list[str] | None,
) -> list[str]:
    if current is None:
        current = []
    if new_errors is None:
        new_errors = []

    return [*current, *new_errors]


def append_completed_agents(
    current: list[AgentRoute] | None,
    new_agents: list[AgentRoute] | None,
) -> list[AgentRoute]:
    if current is None:
        current = []
    if new_agents is None:
        return list(current)

    seen: set[AgentRoute] = set(current)
    result: list[AgentRoute] = list(current)

    for agent in new_agents:
        if agent not in seen:
            seen.add(agent)
            result.append(agent)

    return result
