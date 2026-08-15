import pytest

from app.agents.intent_detection import IntentDetector, detect_intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("How is student 123 progressing?", "progress"),
        ("Is student 123 at risk?", "risk"),
        ("Does student 123 still have valid study rights?", "study_rights"),
        ("Does student 123 have any upcoming deadlines?", "calendar"),
        ("What should I do to help this student?", "recommendation"),
        ("Give me an academic summary of student 123.", "reporting"),
        ("Draft an email to the student about our meeting.", "communication"),
    ],
)
def test_detects_supported_academic_intents(message: str, expected: str) -> None:
    result = detect_intent(message)

    assert result.intent == expected
    assert result.route == expected
    assert result.confidence >= 0.8
    assert result.reason == "matched"
    assert not result.is_ambiguous
    assert result.matched_terms


@pytest.mark.parametrize("message", ["Hi", "Hello!", "What can you help me with?"])
def test_detects_general_conversation(message: str) -> None:
    result = detect_intent(message)

    assert result.intent == "general"
    assert result.route is None
    assert result.reason == "general"
    assert not result.is_ambiguous


def test_vague_academic_request_is_ambiguous() -> None:
    result = detect_intent("Check this student.")

    assert result.intent == "unknown"
    assert result.route is None
    assert result.is_ambiguous
    assert result.reason == "ambiguous"


@pytest.mark.parametrize(
    "message",
    [
        "What is the weather tomorrow?",
        "I made progress on cooking dinner.",
        "Is my computer at risk from malware?",
        "Write a sorting algorithm.",
    ],
)
def test_unsupported_requests_do_not_false_positive(message: str) -> None:
    result = detect_intent(message)

    assert result.intent == "unknown"
    assert result.route is None
    assert result.reason == "unsupported"
    assert not result.is_ambiguous


@pytest.mark.parametrize("message", ["progress", "upcoming events", "reporting"])
def test_existing_explicit_route_aliases_remain_supported(message: str) -> None:
    assert detect_intent(message).route is not None


def test_competing_intents_are_not_arbitrarily_selected() -> None:
    result = detect_intent("Show student progress and academic risk.")

    assert result.intent == "unknown"
    assert result.route is None
    assert result.is_ambiguous


@pytest.mark.parametrize("message", ["", "   ", "\n\t"])
def test_empty_input_is_rejected(message: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        detect_intent(message)


def test_non_string_input_is_rejected() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        IntentDetector().detect(None)  # type: ignore[arg-type]
