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


@pytest.mark.parametrize(
    ("message", "intent", "student_name"),
    [
        ("How is Oskari Example progressing?", "progress", "Oskari Example"),
        ("How is Aava Achiever progressing?", "progress", "Aava Achiever"),
        ("What do you recommend for Oskari Example?", "recommendation", "Oskari Example"),
        ("What do you recommend for Aava Achiever?", "recommendation", "Aava Achiever"),
    ],
)
def test_natural_named_student_requests_keep_route_and_entity_reference(
    message: str, intent: str, student_name: str
) -> None:
    result = detect_intent(message)

    assert result.intent == intent
    assert result.route == intent
    assert result.entity_references == (("STUDENT", student_name),)


@pytest.mark.parametrize(
    ("message", "intent", "student_name"),
    [
        ("What is Alice Smith's academic risk?", "risk", "Alice Smith"),
        ("What is Åsa Berg’s academic risk?", "risk", "Åsa Berg"),
        ("How are John Doe's studies progressing?", "progress", "John Doe"),
        ("What recommendations would you give for Jane Example's studies?", "recommendation", "Jane Example"),
        ("What is Sean O'Brien's academic risk?", "risk", "Sean O'Brien"),
    ],
)
def test_possessive_student_names_are_extracted_without_damaging_name_apostrophes(
    message: str, intent: str, student_name: str
) -> None:
    result = detect_intent(message)

    assert result.intent == intent
    assert result.entity_references == (("STUDENT", student_name),)


@pytest.mark.parametrize(
    ("message", "student_name"),
    [
        ("How is Ada doing?", "Ada"),
        ("Tell me about Ada's progress", "Ada"),
        ("Tell me about Åsa’s progress", "Åsa"),
        ("Show Ada progress", "Ada"),
        ("How Ada Lovelace is progressing?", "Ada Lovelace"),
        ("How Sean O'Brien is progressing?", "Sean O'Brien"),
    ],
)
def test_natural_progress_variations_route_with_clean_student_reference(
    message: str, student_name: str
) -> None:
    result = detect_intent(message)

    assert result.intent == "progress"
    assert result.route == "progress"
    assert result.entity_references == (("STUDENT", student_name),)


@pytest.mark.parametrize(
    ("message", "intent", "student_name"),
    [
        ("how Ada Lovelace doing?", "progress", "Ada Lovelace"),
        ("How Ada Lovelace is doing?", "progress", "Ada Lovelace"),
        ("How is Ada Lovelace progresing?", "progress", "Ada Lovelace"),
        ("Show Ada Lovelace progres", "progress", "Ada Lovelace"),
        ("What is Ada Lovelace acadmic risk?", "risk", "Ada Lovelace"),
        ("What is the risk for Ada Lovelace?", "risk", "Ada Lovelace"),
        ("what you recomend for Ada Lovelace?", "recommendation", "Ada Lovelace"),
        ("What would you recommend for Ada Lovelace?", "recommendation", "Ada Lovelace"),
        ("What should we do for Ada Lovelace?", "recommendation", "Ada Lovelace"),
    ],
)
def test_typo_and_grammar_tolerance_keeps_original_student_reference(
    message: str, intent: str, student_name: str
) -> None:
    result = detect_intent(message)

    assert result.intent == intent
    assert result.entity_references == (("STUDENT", student_name),)


@pytest.mark.parametrize(
    "message",
    [
        "I recomend this movie.",
        "The cooking progres is interesting.",
        "My computer has an acadmic-looking font.",
    ],
)
def test_intent_keyword_typos_without_academic_request_remain_unsupported(message: str) -> None:
    assert detect_intent(message).intent == "unknown"
