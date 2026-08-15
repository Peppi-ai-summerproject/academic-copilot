from typing import cast

import pytest

from app.agents.agent_selection import AgentSelector, RoutingResult
from app.agents.dependency_resolution import DependencyResolver, resolve_dependencies
from app.agents.intent_detection import IntentResult, detect_intent
from app.agents.registry import AgentRegistry
from app.agents.types import AgentRoute


class DummyAgent:
    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError("Dependency resolution must not instantiate agents")


ALL_AGENTS: tuple[AgentRoute, ...] = (
    "calendar",
    "progress",
    "study_rights",
    "risk",
    "recommendation",
    "reporting",
    "communication",
)


def registry_without(*excluded: AgentRoute) -> AgentRegistry:
    registry = AgentRegistry()
    for route in ALL_AGENTS:
        if route not in excluded:
            registry.register(route, DummyAgent)  # type: ignore[arg-type]
    return registry


def routing(*routes: object) -> RoutingResult:
    intent = IntentResult("progress", "progress", 0.9, ("progress",), False, "matched")
    return RoutingResult(
        intent_result=intent,
        selected_routes=cast(tuple[AgentRoute, ...], routes),
        succeeded=True,
        status="selected",
        requires_clarification=False,
        requires_fallback=False,
        reason="test roots",
    )


@pytest.mark.parametrize("route", ["calendar", "progress", "study_rights", "risk", "communication"])
def test_routes_without_required_state_dependencies_remain_single_agent(route: str) -> None:
    result = resolve_dependencies(routing(route), registry_without())

    assert result.succeeded
    assert result.ordered_routes == (route,)


def test_recommendation_runs_after_required_risk_result() -> None:
    result = resolve_dependencies(routing("recommendation"), registry_without())

    assert result.ordered_routes == ("risk", "recommendation")


def test_reporting_expands_all_verified_sections_in_contract_order() -> None:
    result = resolve_dependencies(routing("reporting"), registry_without())

    assert result.ordered_routes == (
        "progress",
        "study_rights",
        "risk",
        "recommendation",
        "reporting",
    )
    assert result.ordered_routes[-1] == "reporting"
    assert len(result.ordered_routes) == len(set(result.ordered_routes))


def test_overlapping_roots_are_deduplicated_and_ordered_deterministically() -> None:
    resolver = DependencyResolver(registry_without())
    roots = routing("risk", "reporting", "risk", "communication")

    first = resolver.resolve(roots)
    second = resolver.resolve(roots)

    expected = (
        "risk",
        "progress",
        "study_rights",
        "recommendation",
        "reporting",
        "communication",
    )
    assert first.ordered_routes == expected
    assert second == first
    assert first.requested_routes == ("risk", "reporting", "communication")


def test_detector_selector_resolver_flow_does_not_execute_workflow() -> None:
    registry = registry_without()
    selected = AgentSelector(registry).select(
        detect_intent("Give me an academic summary of student 123.")
    )

    plan = resolve_dependencies(selected, registry)

    assert plan.ordered_routes == (
        "progress",
        "study_rights",
        "risk",
        "recommendation",
        "reporting",
    )


def test_no_selected_routes_returns_safe_empty_plan() -> None:
    registry = registry_without()
    selected = AgentSelector(registry).select(detect_intent("Hi"))

    plan = resolve_dependencies(selected, registry)

    assert not plan.succeeded
    assert plan.status == "no_routes"
    assert plan.ordered_routes == ()


@pytest.mark.parametrize(
    ("route", "status"),
    [("unsupported", "unsupported_root"), ("finish", "finish_not_allowed")],
)
def test_unsupported_or_finish_root_fails_safely(route: str, status: str) -> None:
    result = resolve_dependencies(routing(route), registry_without())

    assert not result.succeeded
    assert result.status == status
    assert result.ordered_routes == ()


def test_unregistered_requested_route_fails_safely() -> None:
    result = resolve_dependencies(routing("risk"), registry_without("risk"))

    assert not result.succeeded
    assert result.status == "unregistered_root"


def test_missing_registered_dependency_fails_without_partial_plan() -> None:
    result = resolve_dependencies(
        routing("recommendation"),
        registry_without("risk"),
    )

    assert not result.succeeded
    assert result.status == "unregistered_dependency"
    assert result.ordered_routes == ()


def test_cycle_is_detected_safely() -> None:
    dependencies = {
        "risk": ("recommendation",),
        "recommendation": ("risk",),
    }

    result = resolve_dependencies(
        routing("risk"),
        registry_without(),
        cast(dict[AgentRoute, tuple[AgentRoute, ...]], dependencies),
    )

    assert not result.succeeded
    assert result.status == "cycle_detected"
    assert "risk -> recommendation -> risk" in result.reason


@pytest.mark.parametrize(
    "dependencies",
    [
        {"risk": ("not_a_route",)},
        {"risk": ("finish",)},
        {"risk": "progress"},
    ],
)
def test_invalid_dependency_configuration_fails_safely(dependencies: object) -> None:
    result = resolve_dependencies(
        routing("risk"),
        registry_without(),
        cast(dict[AgentRoute, tuple[AgentRoute, ...]], dependencies),
    )

    assert not result.succeeded
    assert result.status in {"invalid_dependency", "finish_not_allowed"}
    assert result.ordered_routes == ()
