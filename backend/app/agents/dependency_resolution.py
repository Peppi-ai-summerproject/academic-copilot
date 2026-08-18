"""Dependency expansion for ordered academic-agent execution plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Protocol, cast

from app.agents.agent_selection import RoutingResult
from app.agents.routing import SUPPORTED_ROUTES
from app.agents.types import AgentRoute


PlanStatus = Literal[
    "planned",
    "no_routes",
    "unsupported_root",
    "unregistered_root",
    "unregistered_dependency",
    "invalid_dependency",
    "finish_not_allowed",
    "cycle_detected",
]

# These rules reflect reads from AgentState.agent_results, not shared data that
# an agent fetches independently through its gateway.
DEFAULT_ROUTE_DEPENDENCIES: Mapping[AgentRoute, tuple[AgentRoute, ...]] = {
    "calendar": (),
    "progress": (),
    "study_rights": (),
    "risk": (),
    "recommendation": ("risk",),
    "reporting": ("progress", "study_rights", "risk", "recommendation"),
    # Communication accepts a variable set of prior results. A communication
    # intent alone carries no information from which to infer those sources.
    "communication": (),
    "academic_data": (),
    "finish": (),
}

_EXECUTABLE_ROUTES = frozenset(route for route in SUPPORTED_ROUTES if route != "finish")


class AgentRegistryView(Protocol):
    def get(self, route: AgentRoute) -> type | None: ...


@dataclass(frozen=True)
class ExecutionPlan:
    """Validated ordered routes suitable for ``AgentState.selected_agents``."""

    routing_result: RoutingResult
    requested_routes: tuple[AgentRoute, ...]
    ordered_routes: tuple[AgentRoute, ...]
    succeeded: bool
    status: PlanStatus
    errors: tuple[str, ...]
    reason: str


class _PlanFailure(Exception):
    def __init__(self, status: PlanStatus, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


class DependencyResolver:
    """Expand selected roots with registered dependencies in topological order."""

    def __init__(
        self,
        registry: AgentRegistryView,
        dependencies: Mapping[AgentRoute, tuple[AgentRoute, ...]] | None = None,
    ) -> None:
        self._registry = registry
        self._dependencies = (
            DEFAULT_ROUTE_DEPENDENCIES if dependencies is None else dependencies
        )

    def resolve(self, routing_result: RoutingResult) -> ExecutionPlan:
        roots = tuple(dict.fromkeys(routing_result.selected_routes))
        if not roots:
            return ExecutionPlan(
                routing_result=routing_result,
                requested_routes=(),
                ordered_routes=(),
                succeeded=False,
                status="no_routes",
                errors=(),
                reason="Routing selected no academic routes to plan.",
            )

        ordered: list[AgentRoute] = []
        visiting: list[AgentRoute] = []
        visited: set[AgentRoute] = set()
        root_set = set(roots)

        def visit(route_value: object, *, dependency: bool) -> None:
            if route_value == "finish":
                raise _PlanFailure(
                    "finish_not_allowed",
                    "The finish route cannot enter an academic execution plan.",
                )
            if route_value not in _EXECUTABLE_ROUTES:
                label = "dependency" if dependency else "requested route"
                raise _PlanFailure(
                    "invalid_dependency" if dependency else "unsupported_root",
                    f"Unsupported {label} '{route_value}'.",
                )

            route = cast(AgentRoute, route_value)
            if route in visiting:
                cycle_start = visiting.index(route)
                cycle = (*visiting[cycle_start:], route)
                raise _PlanFailure(
                    "cycle_detected",
                    f"Dependency cycle detected: {' -> '.join(cycle)}.",
                )
            if route in visited:
                return
            if self._registry.get(route) is None:
                is_root = route in root_set and not dependency
                raise _PlanFailure(
                    "unregistered_root" if is_root else "unregistered_dependency",
                    f"Agent route '{route}' is not registered for execution.",
                )

            raw_dependencies = self._dependencies.get(route, ())
            if not isinstance(raw_dependencies, (tuple, list)):
                raise _PlanFailure(
                    "invalid_dependency",
                    f"Dependencies for '{route}' must be an ordered sequence.",
                )

            visiting.append(route)
            for required in raw_dependencies:
                visit(required, dependency=True)
            visiting.pop()
            visited.add(route)
            ordered.append(route)

        try:
            for root in roots:
                visit(root, dependency=False)
        except _PlanFailure as exc:
            return ExecutionPlan(
                routing_result=routing_result,
                requested_routes=roots,
                ordered_routes=(),
                succeeded=False,
                status=exc.status,
                errors=(exc.reason,),
                reason=exc.reason,
            )

        return ExecutionPlan(
            routing_result=routing_result,
            requested_routes=roots,
            ordered_routes=tuple(ordered),
            succeeded=True,
            status="planned",
            errors=(),
            reason="Expanded registered routes into dependency-safe execution order.",
        )


def resolve_dependencies(
    routing_result: RoutingResult,
    registry: AgentRegistryView,
    dependencies: Mapping[AgentRoute, tuple[AgentRoute, ...]] | None = None,
) -> ExecutionPlan:
    """Convenience entry point for deterministic dependency resolution."""
    return DependencyResolver(registry, dependencies).resolve(routing_result)
