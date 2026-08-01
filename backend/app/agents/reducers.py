"""State reducers for the multi-agent workflow — Issue #87."""

from __future__ import annotations
from app.agents.types import AgentResult


def merge_agent_results(
    current: dict[str, AgentResult],
    update: dict[str, AgentResult],
) -> dict[str, AgentResult]:
    """Merge agent results — last-write-wins on collision."""
    if not update:
        return dict(current)
    if not current:
        return dict(update)
    return {**current, **update}


def append_unique(current: list[str], update: list[str]) -> list[str]:
    """Append items skipping duplicates. Used for completed_agents."""
    if not update:
        return list(current)
    seen = set(current)
    new_items = [item for item in update if item not in seen]
    return list(current) + new_items


def append_all(current: list[str], update: list[str]) -> list[str]:
    """Append all items including duplicates. Used for warnings/errors."""
    if not update:
        return list(current)
    return list(current) + list(update)
