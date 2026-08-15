"""Safe conversion of detected intent into executable agent routes.

Selection is intentionally separate from workflow execution and dependency
expansion.  This module never creates or runs an agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast

from app.agents.intent_detection import IntentResult
from app.agents.routing import SUPPORTED_ROUTES
from app.agents.types import AgentRoute


RoutingStatus = Literal[
    "selected",
    "general",
    "ambiguous",
    "unsupported",
    "invalid_route",
    "unregistered",
    "finish_not_selectable",
]

_ACADEMIC_ROUTES = frozenset(route for route in SUPPORTED_ROUTES if route != "finish")


class AgentRegistryView(Protocol):
    """The read-only part of ``AgentRegistry`` needed during selection."""

    def get(self, route: AgentRoute) -> type | None: ...


@dataclass(frozen=True)
class RoutingResult:
    """Structured output suitable for a later workflow-integration layer."""

    intent_result: IntentResult
    selected_routes: tuple[AgentRoute, ...]
    succeeded: bool
    status: RoutingStatus
    requires_clarification: bool
    requires_fallback: bool
    reason: str

    @property
    def detected_intent(self) -> str:
        return self.intent_result.intent


class AgentSelector:
    """Select at most one registered agent for a structured intent result."""

    def __init__(self, registry: AgentRegistryView) -> None:
        self._registry = registry

    def select(self, intent_result: IntentResult) -> RoutingResult:
        if intent_result.intent == "general":
            return self._no_selection(
                intent_result,
                status="general",
                reason="General conversation does not require an academic agent.",
                requires_fallback=True,
            )

        if intent_result.intent == "unknown":
            ambiguous = intent_result.is_ambiguous or intent_result.reason == "ambiguous"
            return self._no_selection(
                intent_result,
                status="ambiguous" if ambiguous else "unsupported",
                reason=(
                    "The request needs clarification before an agent can be selected."
                    if ambiguous
                    else "The request does not match a supported academic intent."
                ),
                requires_clarification=ambiguous,
                requires_fallback=True,
            )

        route = intent_result.route
        if route == "finish":
            return self._no_selection(
                intent_result,
                status="finish_not_selectable",
                reason="The finish route cannot be selected from a user intent.",
                requires_fallback=True,
            )

        if (
            route is None
            or route not in _ACADEMIC_ROUTES
            or route != intent_result.intent
        ):
            return self._no_selection(
                intent_result,
                status="invalid_route",
                reason="The detected intent does not contain a valid matching agent route.",
                requires_fallback=True,
            )

        typed_route = cast(AgentRoute, route)
        if self._registry.get(typed_route) is None:
            return self._no_selection(
                intent_result,
                status="unregistered",
                reason=f"Agent route '{typed_route}' is not registered for execution.",
                requires_fallback=True,
            )

        return RoutingResult(
            intent_result=intent_result,
            selected_routes=(typed_route,),
            succeeded=True,
            status="selected",
            requires_clarification=False,
            requires_fallback=False,
            reason=f"Selected registered agent route '{typed_route}'.",
        )

    @staticmethod
    def _no_selection(
        intent_result: IntentResult,
        *,
        status: RoutingStatus,
        reason: str,
        requires_clarification: bool = False,
        requires_fallback: bool = False,
    ) -> RoutingResult:
        return RoutingResult(
            intent_result=intent_result,
            selected_routes=(),
            succeeded=False,
            status=status,
            requires_clarification=requires_clarification,
            requires_fallback=requires_fallback,
            reason=reason,
        )


def select_agents(
    intent_result: IntentResult,
    registry: AgentRegistryView,
) -> RoutingResult:
    """Convenience entry point for deterministic, side-effect-free selection."""
    return AgentSelector(registry).select(intent_result)
