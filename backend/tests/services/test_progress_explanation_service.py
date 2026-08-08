"""Tests for deterministic progress explanations — Issue #114."""

from app.services.progress_explanation_service import (
    ProgressExplanationInput,
    ProgressExplanationService,
)


def _result(status: str, completed: int, expected: int, difference: int) -> dict:
    return {
        "success": True,
        "progress": {
            "current_semester": 4,
            "completed_ects": completed,
            "expected_ects": expected,
            "difference_ects": difference,
            "remaining_to_expected_ects": 0 if difference >= 0 else -difference,
            "progress_percentage": 100.0 if difference == 0 else 75.0,
            "status": status,
        },
    }


def _explain(result: dict):
    return ProgressExplanationService().explain(
        ProgressExplanationInput(student_id=7, progress_result=result)
    )


def test_complete_on_track_explanation_preserves_values_and_provenance() -> None:
    explanation = _explain(_result("ON_TRACK", 120, 120, 0))
    assert explanation.data_status == "COMPLETE"
    assert explanation.completed_ects == 120
    assert explanation.expected_ects == 120
    assert explanation.status == "ON_TRACK"
    assert "get_progress.completed_ects" in explanation.evidence
    assert all(
        indicator.source.startswith("get_progress.")
        for indicator in explanation.indicators
    )


def test_behind_ahead_and_equality_use_upstream_classification() -> None:
    behind = _explain(_result("BEHIND", 90, 120, -30))
    ahead = _explain(_result("AHEAD", 150, 120, 30))
    equal = _explain(_result("ON_TRACK", 120, 120, 0))
    assert (behind.status, behind.difference_ects) == ("BEHIND", -30)
    assert (ahead.status, ahead.difference_ects) == ("AHEAD", 30)
    assert (equal.status, equal.difference_ects) == ("ON_TRACK", 0)


def test_missing_expected_or_completed_is_partial_without_invented_values() -> None:
    missing_expected = _result("BEHIND", 90, 120, -30)
    missing_expected["progress"]["expected_ects"] = None
    missing_completed = _result("BEHIND", 90, 120, -30)
    missing_completed["progress"].pop("completed_ects")

    expected_explanation = _explain(missing_expected)
    completed_explanation = _explain(missing_completed)
    assert expected_explanation.data_status == "PARTIAL"
    assert expected_explanation.expected_ects is None
    assert "expected_ects" in expected_explanation.unavailable_fields
    assert completed_explanation.completed_ects is None
    assert "completed_ects" in completed_explanation.unavailable_fields


def test_failed_upstream_result_is_partial_and_has_no_numeric_defaults() -> None:
    explanation = _explain({"success": False, "error": "CURRICULUM_NOT_FOUND"})
    assert explanation.data_status == "PARTIAL"
    assert explanation.completed_ects is None
    assert explanation.expected_ects is None
    assert explanation.indicators == ()
    assert explanation.warnings == ("CURRICULUM_NOT_FOUND",)


def test_explanation_is_deterministic_and_has_no_prescriptive_output() -> None:
    result = _result("BEHIND", 90, 120, -30)
    first = _explain(result).to_dict()
    second = _explain(result).to_dict()
    assert first == second
    assert "risk" not in first
    assert "recommendation" not in first
    assert "intervention" not in first
