"""
Dataset validator for RAG benchmark — Issue #64
Usage: python -m rag.evaluation.validate_dataset
       or: python3 rag/evaluation/validate_dataset.py
"""

import json
import sys
from pathlib import Path
from collections import Counter

VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_QUESTION_TYPES = {"answerable", "unanswerable"}
KNOWN_SOURCES = {
    "Tutoring_Calendar_2025_2026.docx",
    "Academic_Policy_Document.docx",
}
DATASET_PATH = Path(__file__).parent / "datasets" / "rag_test_dataset.json"


def validate(dataset_path: str = str(DATASET_PATH)) -> bool:
    """Validate the benchmark dataset. Returns True if valid."""
    errors = []
    warnings = []

    try:
        with open(dataset_path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"FAIL: Cannot load dataset: {e}")
        return False

    cases = data.get("cases", [])
    if not cases:
        print("FAIL: Dataset contains no cases.")
        return False

    ids = []
    questions = []

    for i, case in enumerate(cases):
        loc = f"Case {i+1} ({case.get('id', '?')})"

        # Required fields
        for field in ["id", "category", "question_type", "difficulty",
                      "question", "expected_answer", "expected_keywords",
                      "expected_sources", "expected_relevant_text"]:
            if field not in case:
                errors.append(f"{loc}: Missing required field '{field}'")

        if "id" in case:
            ids.append(case["id"])

        if "question" in case:
            questions.append(case["question"].strip().lower())

        # Difficulty validation
        if case.get("difficulty") not in VALID_DIFFICULTIES:
            errors.append(f"{loc}: Invalid difficulty '{case.get('difficulty')}'")

        # Question type validation
        if case.get("question_type") not in VALID_QUESTION_TYPES:
            errors.append(f"{loc}: Invalid question_type '{case.get('question_type')}'")

        # Answerable cases must have answers and sources
        if case.get("question_type") == "answerable":
            if not case.get("expected_answer"):
                errors.append(f"{loc}: Answerable case missing expected_answer")
            if not case.get("expected_sources"):
                errors.append(f"{loc}: Answerable case missing expected_sources")
            if not isinstance(case.get("expected_keywords"), list):
                errors.append(f"{loc}: expected_keywords must be a list")

            # Check sources exist
            for src in case.get("expected_sources", []):
                if src not in KNOWN_SOURCES:
                    warnings.append(f"{loc}: Unknown source '{src}'")

        # Unanswerable cases must not have sources
        if case.get("question_type") == "unanswerable":
            if case.get("expected_sources"):
                errors.append(f"{loc}: Unanswerable case should not have expected_sources")

        # No placeholder values
        if case.get("expected_answer") in ["...", "TBD", "TODO", ""]:
            errors.append(f"{loc}: Placeholder expected_answer detected")

    # Unique IDs
    duplicate_ids = [id for id, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        errors.append(f"Duplicate IDs found: {duplicate_ids}")

    # Unique questions
    duplicate_qs = [q for q, count in Counter(questions).items() if count > 1]
    if duplicate_qs:
        errors.append(f"Duplicate questions found: {len(duplicate_qs)}")

    # Print results
    print(f"\nDataset: {dataset_path}")
    print(f"Total cases: {len(cases)}")

    # Stats
    by_type = Counter(c.get("question_type") for c in cases)
    by_diff = Counter(c.get("difficulty") for c in cases)
    by_cat = Counter(c.get("category") for c in cases)

    print(f"\nBy question type:")
    for k, v in sorted(by_type.items()):
        print(f"  {k}: {v}")

    print(f"\nBy difficulty:")
    for k, v in sorted(by_diff.items()):
        print(f"  {k}: {v}")

    print(f"\nBy category:")
    for k, v in sorted(by_cat.items()):
        print(f"  {k}: {v}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  WARNING: {w}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  ERROR: {e}")
        print(f"\nVALIDATION FAILED")
        return False

    print(f"\nVALIDATION PASSED — {len(cases)} cases, {len(errors)} errors, {len(warnings)} warnings")
    return True


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else str(DATASET_PATH)
    success = validate(path)
    sys.exit(0 if success else 1)
