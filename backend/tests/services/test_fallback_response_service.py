from app.agents.intent_detection import IntentResult
from app.services.fallback_response_service import FallbackResponseService


def test_general_response_describes_supported_capabilities() -> None:
    service = FallbackResponseService()
    intent = IntentResult("general", None, 0.95, (), False, "general")

    response = service.for_non_academic(intent).lower()

    for capability in (
        "progress",
        "study rights",
        "academic risk",
        "events",
        "deadlines",
        "recommendations",
        "reports",
    ):
        assert capability in response


def test_ambiguous_response_requests_specific_academic_clarification() -> None:
    service = FallbackResponseService()
    intent = IntentResult("unknown", None, 0.0, (), True, "ambiguous")

    response = service.for_non_academic(intent).lower()

    assert "clarify" in response
    assert "progress" in response
    assert "risk" in response
    assert "study rights" in response
    assert "upcoming events" in response


def test_unsupported_response_explains_scope_without_answering_request() -> None:
    service = FallbackResponseService()
    intent = IntentResult("unknown", None, 0.0, (), False, "unsupported")

    response = service.for_non_academic(intent).lower()

    assert "academic copilot" in response
    assert "focused" in response
    assert "weather" not in response


def test_student_context_requirements_are_centralized_by_route() -> None:
    service = FallbackResponseService()

    assert service.requires_student_context(("risk",))
    assert service.requires_student_context(("progress",))
    assert service.requires_student_context(("reporting",))
    assert not service.requires_student_context(("calendar",))
    assert not service.requires_student_context(("communication",))
