"""Unit tests for ExpectedProgressService — Issue #92.

All tests use fixed, explicit data. No live database, network,
LLM, Qdrant, Telegram, or Gemini is required.

Business rule confirmed from schema:
    expected_ects = curriculum.expected_ects
                    WHERE programme = <student_programme>
                      AND semester  = MAX(course_completions.semester)

The curriculum table stores cumulative ECTS milestones per semester.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.services.expected_progress_service import (
    ExpectedProgressService,
    _find_semester_milestone,
)


# ── Test data — two programmes with different requirements ─────────────────────

BUSINESS_IT_CURRICULUM = {
    "success": True,
    "curriculum": {
        "programme": "Business IT",
        "semesters": [
            {"semester": 1, "expected_ects": 30},
            {"semester": 2, "expected_ects": 60},
            {"semester": 3, "expected_ects": 90},
            {"semester": 4, "expected_ects": 120},
            {"semester": 5, "expected_ects": 150},
            {"semester": 6, "expected_ects": 180},
            {"semester": 7, "expected_ects": 210},
            {"semester": 8, "expected_ects": 240},
        ],
        "total_expected_ects": 240,
    },
}

# Data Engineering uses same structure but demonstrates multiple-programme support
DATA_ENGINEERING_CURRICULUM = {
    "success": True,
    "curriculum": {
        "programme": "Data Engineering",
        "semesters": [
            {"semester": 1, "expected_ects": 30},
            {"semester": 2, "expected_ects": 60},
            {"semester": 3, "expected_ects": 90},
            {"semester": 4, "expected_ects": 120},
            {"semester": 5, "expected_ects": 150},
            {"semester": 6, "expected_ects": 180},
            {"semester": 7, "expected_ects": 210},
            {"semester": 8, "expected_ects": 240},
        ],
        "total_expected_ects": 240,
    },
}

CURRICULUM_NOT_FOUND = {
    "success": False,
    "error": "CURRICULUM_NOT_FOUND",
    "message": "Curriculum data was not found for programme 'Unknown'.",
}


def _progress(
    student_id=1,
    student_number="S001",
    name="Mikael Virtanen",
    programme="Business IT",
    completed_ects=60,
    expected_ects=60,
    current_semester=2,
    status="ON_TRACK",
):
    return {
        "success": True,
        "progress": {
            "student_id": student_id,
            "student_number": student_number,
            "student_name": name,
            "programme": programme,
            "current_semester": current_semester,
            "completed_ects": completed_ects,
            "expected_ects": expected_ects,
            "difference_ects": completed_ects - expected_ects,
            "remaining_to_expected_ects": max(expected_ects - completed_ects, 0),
            "progress_percentage": round(completed_ects / expected_ects * 100, 2) if expected_ects else 0.0,
            "status": status,
        },
    }


def _make_service(progress_result=None, curriculum_result=None):
    progress_svc = Mock()
    progress_svc.get_progress.return_value = (
        progress_result if progress_result is not None else _progress()
    )
    curriculum_svc = Mock()
    curriculum_svc.get_curriculum.return_value = (
        curriculum_result if curriculum_result is not None
        else BUSINESS_IT_CURRICULUM
    )
    return ExpectedProgressService(
        progress_service=progress_svc,
        curriculum_service=curriculum_svc,
    ), progress_svc, curriculum_svc


# ── Input validation ──────────────────────────────────────────────────────────

def test_invalid_student_id_zero_returns_error():
    svc, _, _ = _make_service()
    result = svc.get_expected_progress(0)
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


def test_invalid_student_id_negative_returns_error():
    svc, _, _ = _make_service()
    result = svc.get_expected_progress(-1)
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


def test_invalid_student_id_string_returns_error():
    svc, _, _ = _make_service()
    result = svc.get_expected_progress("abc")
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


# ── Student not found ─────────────────────────────────────────────────────────

def test_missing_student_returns_not_found_error():
    svc, _, _ = _make_service(
        progress_result={
            "success": False,
            "error": "STUDENT_NOT_FOUND",
            "message": "Student not found.",
        }
    )
    result = svc.get_expected_progress(999)
    assert result["success"] is False
    assert result["error"] == "STUDENT_NOT_FOUND"


def test_missing_student_does_not_call_curriculum_service():
    svc, _, curriculum_svc = _make_service(
        progress_result={
            "success": False,
            "error": "STUDENT_NOT_FOUND",
            "message": "Not found.",
        }
    )
    svc.get_expected_progress(999)
    curriculum_svc.get_curriculum.assert_not_called()


# ── Curriculum not found ──────────────────────────────────────────────────────

def test_missing_curriculum_returns_error():
    svc, _, _ = _make_service(curriculum_result=CURRICULUM_NOT_FOUND)
    result = svc.get_expected_progress(1)
    assert result["success"] is False
    assert result["error"] == "CURRICULUM_NOT_FOUND"


# ── Successful expected progress calculation ──────────────────────────────────

def test_returns_success_true_for_valid_student():
    svc, _, _ = _make_service()
    result = svc.get_expected_progress(1)
    assert result["success"] is True


def test_returns_expected_progress_section():
    svc, _, _ = _make_service()
    result = svc.get_expected_progress(1)
    assert "expected_progress" in result


def test_expected_ects_matches_semester_milestone():
    # Student at semester 2 → expected 60 ECTS
    svc, _, _ = _make_service(progress_result=_progress(current_semester=2))
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["expected_ects"] == 60


def test_expected_ects_semester_1():
    svc, _, _ = _make_service(progress_result=_progress(current_semester=1))
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["expected_ects"] == 30


def test_expected_ects_semester_4():
    svc, _, _ = _make_service(progress_result=_progress(current_semester=4))
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["expected_ects"] == 120


def test_expected_ects_semester_8_equals_total():
    svc, _, _ = _make_service(progress_result=_progress(current_semester=8))
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["expected_ects"] == 240
    assert result["expected_progress"]["total_curriculum_ects"] == 240


def test_total_curriculum_ects_is_maximum_semester_milestone():
    svc, _, _ = _make_service()
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["total_curriculum_ects"] == 240


def test_remaining_to_graduation_calculated_correctly():
    # At semester 4, expected=120, total=240 → remaining=120
    svc, _, _ = _make_service(progress_result=_progress(current_semester=4))
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["remaining_to_graduation"] == 120


def test_remaining_to_graduation_zero_at_final_semester():
    svc, _, _ = _make_service(progress_result=_progress(current_semester=8))
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["remaining_to_graduation"] == 0


def test_remaining_to_graduation_not_negative():
    # Even if somehow expected > total (data issue), should be 0
    svc, _, _ = _make_service(progress_result=_progress(current_semester=8))
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["remaining_to_graduation"] >= 0


def test_semester_milestones_returned():
    svc, _, _ = _make_service()
    result = svc.get_expected_progress(1)
    milestones = result["expected_progress"]["semester_milestones"]
    assert isinstance(milestones, list)
    assert len(milestones) == 8


def test_student_info_in_result():
    svc, _, _ = _make_service(
        progress_result=_progress(student_number="S001", name="Mikael Virtanen")
    )
    result = svc.get_expected_progress(1)
    ep = result["expected_progress"]
    assert ep["student_number"] == "S001"
    assert ep["student_name"] == "Mikael Virtanen"
    assert ep["programme"] == "Business IT"


def test_current_semester_in_result():
    svc, _, _ = _make_service(progress_result=_progress(current_semester=3))
    result = svc.get_expected_progress(1)
    assert result["expected_progress"]["current_semester"] == 3


# ── Multiple programme support ────────────────────────────────────────────────

def test_two_students_different_programmes_same_semester():
    """Two programmes with same structure produce same milestone at same semester."""
    progress_svc = Mock()
    curriculum_svc = Mock()

    # Student 1: Business IT, semester 4
    progress_svc.get_progress.return_value = _progress(
        student_id=1, programme="Business IT", current_semester=4
    )
    curriculum_svc.get_curriculum.return_value = BUSINESS_IT_CURRICULUM
    svc1 = ExpectedProgressService(progress_svc, curriculum_svc)
    result1 = svc1.get_expected_progress(1)

    # Student 2: Data Engineering, semester 4
    progress_svc2 = Mock()
    curriculum_svc2 = Mock()
    progress_svc2.get_progress.return_value = _progress(
        student_id=2, programme="Data Engineering", current_semester=4
    )
    curriculum_svc2.get_curriculum.return_value = DATA_ENGINEERING_CURRICULUM
    svc2 = ExpectedProgressService(progress_svc2, curriculum_svc2)
    result2 = svc2.get_expected_progress(2)

    assert result1["expected_progress"]["expected_ects"] == 120
    assert result2["expected_progress"]["expected_ects"] == 120
    # Different programmes are correctly identified
    assert result1["expected_progress"]["programme"] == "Business IT"
    assert result2["expected_progress"]["programme"] == "Data Engineering"


def test_curriculum_service_called_with_correct_programme():
    svc, _, curriculum_svc = _make_service(
        progress_result=_progress(programme="Data Engineering")
    )
    svc.get_expected_progress(1)
    curriculum_svc.get_curriculum.assert_called_once_with("Data Engineering")


def test_no_hardcoded_programme_branches():
    """Verify the service delegates to curriculum_service, not conditionals."""
    progress_svc = Mock()
    curriculum_svc = Mock()

    # Use a fictional programme — should still work if curriculum exists
    fictional_curriculum = {
        "success": True,
        "curriculum": {
            "programme": "Fictional Programme",
            "semesters": [
                {"semester": 1, "expected_ects": 20},
                {"semester": 2, "expected_ects": 40},
            ],
            "total_expected_ects": 40,
        },
    }
    progress_svc.get_progress.return_value = _progress(
        programme="Fictional Programme", current_semester=1
    )
    curriculum_svc.get_curriculum.return_value = fictional_curriculum
    svc = ExpectedProgressService(progress_svc, curriculum_svc)
    result = svc.get_expected_progress(1)

    assert result["success"] is True
    assert result["expected_progress"]["expected_ects"] == 20
    assert result["expected_progress"]["total_curriculum_ects"] == 40


# ── Missing semester milestone ────────────────────────────────────────────────

def test_missing_semester_in_curriculum_returns_error():
    """Student at semester 9 but curriculum only has 8 semesters."""
    svc, _, _ = _make_service(
        progress_result=_progress(current_semester=9)
    )
    result = svc.get_expected_progress(1)
    assert result["success"] is False
    assert result["error"] == "SEMESTER_MILESTONE_NOT_FOUND"


# ── get_expected_ects_for_semester ────────────────────────────────────────────

def test_get_expected_ects_for_semester_success():
    svc, _, _ = _make_service()
    result = svc.get_expected_ects_for_semester("Business IT", 4)
    assert result["success"] is True
    assert result["expected_ects"] == 120


def test_get_expected_ects_for_semester_empty_programme():
    svc, _, _ = _make_service()
    result = svc.get_expected_ects_for_semester("", 4)
    assert result["success"] is False
    assert result["error"] == "INVALID_PROGRAMME"


def test_get_expected_ects_for_semester_invalid_semester():
    svc, _, _ = _make_service()
    result = svc.get_expected_ects_for_semester("Business IT", 0)
    assert result["success"] is False
    assert result["error"] == "INVALID_SEMESTER"


def test_get_expected_ects_for_semester_missing_curriculum():
    svc, _, _ = _make_service(curriculum_result=CURRICULUM_NOT_FOUND)
    result = svc.get_expected_ects_for_semester("Unknown", 1)
    assert result["success"] is False
    assert result["error"] == "CURRICULUM_NOT_FOUND"


def test_get_expected_ects_for_semester_missing_milestone():
    svc, _, _ = _make_service()
    result = svc.get_expected_ects_for_semester("Business IT", 99)
    assert result["success"] is False
    assert result["error"] == "SEMESTER_MILESTONE_NOT_FOUND"


# ── Determinism — no datetime.today() dependency ──────────────────────────────

def test_calculation_is_deterministic_no_date_dependency():
    """Same inputs must always produce same expected_ects.
    This test verifies the calculation does not depend on the current date."""
    svc1, _, _ = _make_service(progress_result=_progress(current_semester=4))
    svc2, _, _ = _make_service(progress_result=_progress(current_semester=4))
    result1 = svc1.get_expected_progress(1)
    result2 = svc2.get_expected_progress(1)
    assert result1["expected_progress"]["expected_ects"] == result2["expected_progress"]["expected_ects"]


# ── Issue #91 compatibility ───────────────────────────────────────────────────

def test_does_not_recalculate_completed_ects():
    """#92 must not return or calculate completed_ects — that belongs to #91."""
    svc, _, _ = _make_service()
    result = svc.get_expected_progress(1)
    ep = result["expected_progress"]
    # completed_ects must NOT be in the expected_progress result
    assert "completed_ects" not in ep
    assert "is_behind" not in ep
    assert "is_ahead" not in ep


def test_progress_service_called_with_correct_student_id():
    svc, progress_svc, _ = _make_service()
    svc.get_expected_progress(42)
    progress_svc.get_progress.assert_called_once_with(42)


def test_result_does_not_contain_delay_or_risk_fields():
    """#92 must not implement #93, #94, #95 functionality."""
    svc, _, _ = _make_service()
    result = svc.get_expected_progress(1)
    ep = result.get("expected_progress", {})
    forbidden = [
        "is_delayed", "delay_status", "risk_level", "risk_score",
        "academic_health_score", "recommendation", "warning_message",
        "completed_ects", "difference_ects", "is_behind", "is_ahead",
    ]
    for field in forbidden:
        assert field not in ep, f"Field '{field}' should not be in #92 result"


# ── _find_semester_milestone helper ──────────────────────────────────────────

def test_find_semester_milestone_found():
    semesters = [
        {"semester": 1, "expected_ects": 30},
        {"semester": 2, "expected_ects": 60},
        {"semester": 3, "expected_ects": 90},
    ]
    assert _find_semester_milestone(semesters, 2) == 60


def test_find_semester_milestone_not_found():
    semesters = [{"semester": 1, "expected_ects": 30}]
    assert _find_semester_milestone(semesters, 5) is None


def test_find_semester_milestone_empty_list():
    assert _find_semester_milestone([], 1) is None


def test_find_semester_milestone_first_semester():
    semesters = [
        {"semester": 1, "expected_ects": 30},
        {"semester": 2, "expected_ects": 60},
    ]
    assert _find_semester_milestone(semesters, 1) == 30


def test_find_semester_milestone_last_semester():
    semesters = [
        {"semester": 7, "expected_ects": 210},
        {"semester": 8, "expected_ects": 240},
    ]
    assert _find_semester_milestone(semesters, 8) == 240
