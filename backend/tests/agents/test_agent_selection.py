from typing import cast

import pytest

from app.agents.agent_selection import AgentSelector, select_agents
from app.agents.intent_detection import IntentName, IntentResult, detect_intent
from app.agents.registry import AgentRegistry
from app.agents.routing import SUPPORTED_ROUTES
from app.agents.types import AgentRoute


class DummyAgent:
    """Registration marker; selection must never instantiate this class."""

    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError("The selector must not instantiate agents")


ACADEMIC_ROUTES = (
    "calendar",
    "progress",
    "study_rights",
    "risk",
    "recommendation",
    "reporting",
    "communication",
)


def registered_registry(*routes: AgentRoute) -> AgentRegistry:
    registry = AgentRegistry()
    for route in routes:
        registry.register(route, DummyAgent)  # type: ignore[arg-type]
    return registry


def matched_intent(route: str) -> IntentResult:
    return IntentResult(
        intent=cast(IntentName, route),
        route=cast(AgentRoute, route),
        confidence=0.9,
        matched_terms=(route,),
        is_ambiguous=False,
        reason="matched",
    )


@pytest.mark.parametrize("route", ACADEMIC_ROUTES)
def test_each_academic_intent_selects_its_single_registered_route(route: str) -> None:
    typed_route = cast(AgentRoute, route)
    result = select_agents(matched_intent(route), registered_registry(typed_route))

    assert result.detected_intent == route
    assert result.selected_routes == (route,)
    assert result.succeeded
    assert result.status == "selected"
    assert not result.requires_clarification
    assert not result.requires_fallback
    assert len(result.selected_routes) == len(set(result.selected_routes))
    assert result.selected_routes[0] in SUPPORTED_ROUTES


@pytest.mark.parametrize(
    ("intent", "expected_status", "clarification"),
    [
        (IntentResult("general", None, 0.95, (), False, "general"), "general", False),
        (IntentResult("unknown", None, 0.0, (), False, "unsupported"), "unsupported", False),
        (IntentResult("unknown", None, 0.0, (), True, "ambiguous"), "ambiguous", True),
    ],
)
def test_non_academic_intents_select_nothing(
    intent: IntentResult,
    expected_status: str,
    clarification: bool,
) -> None:
    result = AgentSelector(registered_registry(*ACADEMIC_ROUTES)).select(intent)

    assert result.selected_routes == ()
    assert not result.succeeded
    assert result.status == expected_status
    assert result.requires_clarification is clarification
    assert result.requires_fallback


def test_unregistered_route_fails_safely() -> None:
    result = select_agents(matched_intent("risk"), registered_registry())

    assert result.selected_routes == ()
    assert not result.succeeded
    assert result.status == "unregistered"
    assert result.requires_fallback


@pytest.mark.parametrize(
    "intent",
    [
        IntentResult("risk", None, 0.9, ("risk",), False, "matched"),
        IntentResult(
            "risk",
            cast(AgentRoute, "not_a_route"),
            0.9,
            ("risk",),
            False,
            "matched",
        ),
        IntentResult("risk", "progress", 0.9, ("risk",), False, "matched"),
    ],
)
def test_invalid_or_mismatched_route_cannot_be_returned(intent: IntentResult) -> None:
    registry = registered_registry("risk", "progress")
    result = select_agents(intent, registry)

    assert result.selected_routes == ()
    assert not result.succeeded
    assert result.status == "invalid_route"


def test_finish_cannot_be_selected_from_user_intent() -> None:
    intent = IntentResult("risk", "finish", 0.9, ("finish",), False, "matched")
    result = select_agents(intent, registered_registry("finish"))

    assert result.selected_routes == ()
    assert result.status == "finish_not_selectable"


def test_output_is_deterministic() -> None:
    selector = AgentSelector(registered_registry("progress"))
    intent = matched_intent("progress")

    assert selector.select(intent) == selector.select(intent)


def test_detected_risk_intent_selects_only_risk_without_execution() -> None:
    intent = detect_intent("Is student 123 at risk?")

    result = select_agents(intent, registered_registry("risk"))

    assert result.selected_routes == ("risk",)
