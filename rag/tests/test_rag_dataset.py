"""Unit tests for RAG benchmark dataset — Issue #64."""

import json
import pytest
from pathlib import Path
from collections import Counter

DATASET_PATH = Path(__file__).parent.parent / "evaluation" / "datasets" / "rag_test_dataset.json"
KNOWN_SOURCES = {
    "Tutoring_Calendar_2025_2026.docx",
    "Academic_Policy_Document.docx",
}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_QUESTION_TYPES = {"answerable", "unanswerable"}


@pytest.fixture(scope="module")
def dataset():
    with open(DATASET_PATH) as f:
        return json.load(f)

@pytest.fixture(scope="module")
def cases(dataset):
    return dataset["cases"]


def test_dataset_file_loads(dataset):
    assert isinstance(dataset, dict)
    assert "cases" in dataset
    assert len(dataset["cases"]) > 0

def test_minimum_dataset_size(cases):
    assert len(cases) >= 40, f"Expected at least 40 cases, got {len(cases)}"

def test_all_required_fields_present(cases):
    required = ["id", "category", "question_type", "difficulty",
                "question", "expected_answer", "expected_keywords",
                "expected_sources", "expected_relevant_text"]
    for case in cases:
        for field in required:
            assert field in case, f"Case {case.get('id')} missing field '{field}'"

def test_unique_ids(cases):
    ids = [c["id"] for c in cases]
    duplicates = [id for id, count in Counter(ids).items() if count > 1]
    assert not duplicates, f"Duplicate IDs: {duplicates}"

def test_unique_questions(cases):
    questions = [c["question"].strip().lower() for c in cases]
    duplicates = [q for q, count in Counter(questions).items() if count > 1]
    assert not duplicates, f"Duplicate questions found: {len(duplicates)}"

def test_valid_difficulty_values(cases):
    for case in cases:
        assert case["difficulty"] in VALID_DIFFICULTIES,             f"Case {case['id']} has invalid difficulty: {case['difficulty']}"

def test_valid_question_types(cases):
    for case in cases:
        assert case["question_type"] in VALID_QUESTION_TYPES,             f"Case {case['id']} has invalid question_type: {case['question_type']}"

def test_answerable_cases_have_expected_answers(cases):
    for case in cases:
        if case["question_type"] == "answerable":
            assert case["expected_answer"],                 f"Case {case['id']} is answerable but has no expected_answer"

def test_answerable_cases_have_expected_sources(cases):
    for case in cases:
        if case["question_type"] == "answerable":
            assert case["expected_sources"],                 f"Case {case['id']} is answerable but has no expected_sources"

def test_expected_keywords_is_list(cases):
    for case in cases:
        assert isinstance(case["expected_keywords"], list),             f"Case {case['id']} expected_keywords must be a list"

def test_expected_sources_are_known(cases):
    for case in cases:
        for src in case.get("expected_sources", []):
            assert src in KNOWN_SOURCES,                 f"Case {case['id']} references unknown source: {src}"

def test_unanswerable_cases_have_no_sources(cases):
    for case in cases:
        if case["question_type"] == "unanswerable":
            assert not case.get("expected_sources"),                 f"Case {case['id']} is unanswerable but has expected_sources"

def test_both_question_types_present(cases):
    types = {c["question_type"] for c in cases}
    assert "answerable" in types
    assert "unanswerable" in types

def test_all_difficulties_present(cases):
    difficulties = {c["difficulty"] for c in cases}
    assert "easy" in difficulties
    assert "medium" in difficulties
    assert "hard" in difficulties

def test_minimum_category_coverage(cases):
    categories = {c["category"] for c in cases}
    assert len(categories) >= 5, f"Expected at least 5 categories, got {len(categories)}"

def test_unanswerable_ratio(cases):
    total = len(cases)
    unanswerable = sum(1 for c in cases if c["question_type"] == "unanswerable")
    ratio = unanswerable / total
    assert 0.05 <= ratio <= 0.30,         f"Unanswerable ratio {ratio:.1%} outside expected range 5-30%"

def test_no_placeholder_answers(cases):
    placeholders = {"...", "TBD", "TODO"}
    for case in cases:
        assert case.get("expected_answer") not in placeholders,             f"Case {case['id']} has placeholder answer"

def test_questions_are_nonempty(cases):
    for case in cases:
        assert case["question"].strip(), f"Case {case['id']} has empty question"

def test_compatible_with_issue63_evaluator(cases):
    """Verify dataset is compatible with Issue #63 EvaluationQuery schema."""
    from rag.evaluation.models import EvaluationQuery
    for case in cases:
        if case["question_type"] == "answerable":
            query = EvaluationQuery(
                id=case["id"],
                question=case["question"],
                category=case["category"],
                expected_keywords=case["expected_keywords"],
            )
            assert query.id == case["id"]
            assert query.question == case["question"]

def test_validator_passes_on_valid_dataset():
    from rag.evaluation.validate_dataset import validate
    assert validate(str(DATASET_PATH)) is True

def test_validator_rejects_missing_field(tmp_path):
    from rag.evaluation.validate_dataset import validate
    bad_dataset = {
        "cases": [
            {"id": "X001", "question": "test?"}
        ]
    }
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad_dataset))
    assert validate(str(bad_path)) is False

def test_validator_rejects_duplicate_ids(tmp_path):
    from rag.evaluation.validate_dataset import validate
    bad_dataset = {
        "cases": [
            {"id": "X001", "category": "c", "question_type": "unanswerable",
             "difficulty": "easy", "question": "Q1?", "expected_answer": "A",
             "expected_keywords": [], "expected_sources": [], "expected_relevant_text": ""},
            {"id": "X001", "category": "c", "question_type": "unanswerable",
             "difficulty": "easy", "question": "Q2?", "expected_answer": "A",
             "expected_keywords": [], "expected_sources": [], "expected_relevant_text": ""},
        ]
    }
    bad_path = tmp_path / "bad2.json"
    bad_path.write_text(json.dumps(bad_dataset))
    assert validate(str(bad_path)) is False
