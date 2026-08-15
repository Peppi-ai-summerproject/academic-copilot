"""Cross-layer regression tests for the complete request-routing pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.agents.agent_selection import AgentSelector, RoutingResult
from app.agents.dependency_resolution import DependencyResolver, ExecutionPlan
from app.agents.intent_detection import IntentResult, detect_intent
from app.agents.registry import AgentRegistry
from app.agents.routing import SUPPORTED_ROUTES


class DummyAgent:
    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError("Routing tests must not instantiate academic agents")


ACADEMIC_ROUTES = tuple(
    route for route in SUPPORTED_ROUTES if route != "finish"
)


@dataclass(frozen=True)
class PipelineResult:
    intent: IntentResult
    routing: RoutingResult
    plan: ExecutionPlan


def complete_registry() -> AgentRegistry:
    registry = AgentRegistry()
    for route in ACADEMIC_ROUTES:
        registry.register(route, DummyAgent)  # type: ignore[arg-type]
    return registry


def route_request(message: str, registry: AgentRegistry | None = None) -> PipelineResult:
    active_registry = registry or complete_registry()
    intent = detect_intent(message)
    routing = AgentSelector(active_registry).select(intent)
    plan = DependencyResolver(active_registry).resolve(routing)
    return PipelineResult(intent, routing, plan)


@pytest.mark.parametrize(
    ("message", "intent", "root", "ordered"),
    [
        (
            "How is student 123 progressing?",
            "progress",
            "progress",
            ("progress",),
        ),
        ("Is student 123 at risk?", "risk", "risk", ("risk",)),
        (
            "Does student 123 still have valid study rights?",
            "study_rights",
            "study_rights",
            ("study_rights",),
        ),
        (
            "What deadlines does student 123 have coming up?",
            "calendar",
            "calendar",
            ("calendar",),
        ),
        (
            "What should I do to help this student?",
            "recommendation",
            "recommendation",
            ("risk", "recommendation"),
        ),
        (
            "Give me an academic summary for student 123.",
            "reporting",
            "reporting",
            ("progress", "study_rights", "risk", "recommendation", "reporting"),
        ),
        (
            "Draft a message to the student about their academic progress.",
            "communication",
            "communication",
            ("communication",),
        ),
    ],
)
def test_canonical_academic_request_routes_through_complete_pipeline(
    message: str,
    intent: str,
    root: str,
    ordered: tuple[str, ...],
) -> None:
    registry = complete_registry()
    result = route_request(message, registry)

    assert result.intent.intent == intent
    assert result.routing.selected_routes == (root,)
    assert result.routing.status == "selected"
    assert result.plan.requested_routes == (root,)
    assert result.plan.ordered_routes == ordered
    assert result.plan.status == "planned"
    assert result.plan.succeeded
    assert len(result.plan.ordered_routes) == len(set(result.plan.ordered_routes))
    for route in result.plan.ordered_routes:
        assert route in SUPPORTED_ROUTES
        assert route != "finish"
        assert registry.get(route) is not None


@pytest.mark.parametrize("message", ["Hi", "What can you help me with?"])
def test_general_request_produces_no_academic_plan(message: str) -> None:
    result = route_request(message)

    assert result.intent.intent == "general"
    assert result.intent.route is None
    assert result.routing.selected_routes == ()
    assert not result.routing.succeeded
    assert result.plan.ordered_routes == ()
    assert result.plan.status == "no_routes"


def test_ambiguous_academic_request_requires_clarification_and_no_plan() -> None:
    result = route_request("Check this student.")

    assert result.intent.intent == "unknown"
    assert result.intent.is_ambiguous
    assert result.routing.status == "ambiguous"
    assert result.routing.requires_clarification
    assert result.routing.selected_routes == ()
    assert result.plan.ordered_routes == ()


def test_unsupported_request_produces_no_arbitrary_academic_plan() -> None:
    result = route_request("What's the weather today?")

    assert result.intent.intent == "unknown"
    assert result.intent.reason == "unsupported"
    assert not result.intent.is_ambiguous
    assert result.routing.status == "unsupported"
    assert result.routing.selected_routes == ()
    assert result.plan.ordered_routes == ()


@pytest.mark.parametrize(
    "message",
    [
        "How is student 123 progressing?",
        "Is student 123 at risk?",
        "Give me an academic summary for student 123.",
        "Check this student.",
    ],
)
def test_complete_pipeline_is_deterministic(message: str) -> None:
    registry = complete_registry()

    first = route_request(message, registry)
    second = route_request(message, registry)
    third = route_request(message, registry)

    assert first == second == third


def test_unregistered_route_cannot_become_an_execution_plan() -> None:
    registry = AgentRegistry()
    intent = detect_intent("Is student 123 at risk?")
    routing = AgentSelector(registry).select(intent)
    plan = DependencyResolver(registry).resolve(routing)

    assert routing.status == "unregistered"
    assert routing.selected_routes == ()
    assert plan.status == "no_routes"
    assert plan.ordered_routes == ()
