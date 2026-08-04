"""Unit tests for DelayDetectionService and detect_delay — Issue #93.

All tests use fixed inputs. No live database, network, LLM,
Qdrant, Telegram, or Gemini is required.

Detection rule (confirmed from risk_policy.py and progress_service.py):
    is_delayed      = completed_ects < expected_ects
    delay_ects      = max(expected_ects - completed_ects, 0)
    difference_ects = completed_ects - expected_ects  (signed)
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.services.delay_detection_service import (
    DelayDetectionService,
    detect_delay,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _progress_result(
    student_id=1,
    student_number="S001",
    student_name="Mikael Virtanen",
    programme="Business IT",
    current_semester=4,
    completed_ects=60,
    expected_ects=120,
    status="BEHIND",
):
    difference = completed_ects - expected_ects
    return {
        "success": True,
        "progress": {
            "student_id": student_id,
            "student_number": student_number,
            "student_name": student_name,
            "programme": programme,
            "current_semester": current_semester,
            "completed_ects": completed_ects,
            "expected_ects": expected_ects,
            "difference_ects": difference,
            "remaining_to_expected_ects": max(expected_ects - completed_ects, 0),
            "progress_percentage": round(completed_ects / expected_ects * 100, 2) if expected_ects else 0.0,
            "status": status,
        },
    }


def _make_service(progress_result=None):
    progress_svc = Mock()
    progress_svc.get_progress.return_value = (
        progress_result if progress_result is not None
        else _progress_result()
    )
    return DelayDetectionService(progress_service=progress_svc), progress_svc


# ── Pure detect_delay function tests ──────────────────────────────────────────

def test_detect_delay_behind_is_delayed():
    result = detect_delay(completed_ects=60, expected_ects=120)
    assert result["is_delayed"] is True


def test_detect_delay_behind_delay_ects():
    result = detect_delay(completed_ects=60, expected_ects=120)
    assert result["delay_ects"] == 60


def test_detect_delay_behind_difference_ects_is_negative():
    result = detect_delay(completed_ects=60, expected_ects=120)
    assert result["difference_ects"] == -60


def test_detect_delay_on_track_not_delayed():
    result = detect_delay(completed_ects=120, expected_ects=120)
    assert result["is_delayed"] is False


def test_detect_delay_on_track_delay_ects_zero():
    result = detect_delay(completed_ects=120, expected_ects=120)
    assert result["delay_ects"] == 0


def test_detect_delay_on_track_difference_ects_zero():
    result = detect_delay(completed_ects=120, expected_ects=120)
    assert result["difference_ects"] == 0


def test_detect_delay_ahead_not_delayed():
    result = detect_delay(completed_ects=150, expected_ects=120)
    assert result["is_delayed"] is False


def test_detect_delay_ahead_delay_ects_zero():
    result = detect_delay(completed_ects=150, expected_ects=120)
    assert result["delay_ects"] == 0


def test_detect_delay_ahead_difference_ects_positive():
    result = detect_delay(completed_ects=150, expected_ects=120)
    assert result["difference_ects"] == 30


def test_detect_delay_zero_completed_positive_expected():
    result = detect_delay(completed_ects=0, expected_ects=60)
    assert result["is_delayed"] is True
    assert result["delay_ects"] == 60
    assert result["difference_ects"] == -60


def test_detect_delay_both_zero_not_delayed():
    result = detect_delay(completed_ects=0, expected_ects=0)
    assert result["is_delayed"] is False
    assert result["delay_ects"] == 0
    assert result["difference_ects"] == 0


def test_detect_delay_delay_ects_never_negative():
    # Ahead by 30 — delay_ects must be 0, not -30
    result = detect_delay(completed_ects=150, expected_ects=120)
    assert result["delay_ects"] >= 0


def test_detect_delay_small_deficit():
    result = detect_delay(completed_ects=119, expected_ects=120)
    assert result["is_delayed"] is True
    assert result["delay_ects"] == 1


def test_detect_delay_large_deficit():
    result = detect_delay(completed_ects=0, expected_ects=240)
    assert result["is_delayed"] is True
    assert result["delay_ects"] == 240


def test_detect_delay_zero_expected_not_delayed():
    # When expected is 0 (e.g. semester 0), no deficit possible
    result = detect_delay(completed_ects=0, expected_ects=0)
    assert result["is_delayed"] is False
    assert result["delay_ects"] == 0


def test_detect_delay_returns_all_required_fields():
    result = detect_delay(completed_ects=60, expected_ects=120)
    assert "is_delayed" in result
    assert "delay_ects" in result
    assert "difference_ects" in result


def test_detect_delay_is_deterministic():
    """Same inputs always produce same result — no date.today() dependency."""
    r1 = detect_delay(completed_ects=60, expected_ects=120)
    r2 = detect_delay(completed_ects=60, expected_ects=120)
    assert r1 == r2


# ── DelayDetectionService tests ───────────────────────────────────────────────

def test_service_returns_success_true_for_delayed_student():
    svc, _ = _make_service(_progress_result(completed_ects=60, expected_ects=120))
    result = svc.detect_student_delay(1)
    assert result["success"] is True


def test_service_returns_delay_section():
    svc, _ = _make_service()
    result = svc.detect_student_delay(1)
    assert "delay" in result


def test_service_delayed_student_is_delayed_true():
    svc, _ = _make_service(_progress_result(completed_ects=60, expected_ects=120))
    result = svc.detect_student_delay(1)
    assert result["delay"]["is_delayed"] is True


def test_service_delayed_student_delay_ects():
    svc, _ = _make_service(_progress_result(completed_ects=60, expected_ects=120))
    result = svc.detect_student_delay(1)
    assert result["delay"]["delay_ects"] == 60


def test_service_delayed_student_difference_ects():
    svc, _ = _make_service(_progress_result(completed_ects=60, expected_ects=120))
    result = svc.detect_student_delay(1)
    assert result["delay"]["difference_ects"] == -60


def test_service_on_track_student_not_delayed():
    svc, _ = _make_service(
        _progress_result(completed_ects=120, expected_ects=120, status="ON_TRACK")
    )
    result = svc.detect_student_delay(1)
    assert result["delay"]["is_delayed"] is False
    assert result["delay"]["delay_ects"] == 0


def test_service_ahead_student_not_delayed():
    svc, _ = _make_service(
        _progress_result(completed_ects=150, expected_ects=120, status="AHEAD")
    )
    result = svc.detect_student_delay(1)
    assert result["delay"]["is_delayed"] is False
    assert result["delay"]["delay_ects"] == 0
    assert result["delay"]["difference_ects"] == 30


def test_service_zero_completed_is_delayed():
    svc, _ = _make_service(
        _progress_result(completed_ects=0, expected_ects=60, status="BEHIND")
    )
    result = svc.detect_student_delay(1)
    assert result["delay"]["is_delayed"] is True
    assert result["delay"]["delay_ects"] == 60
    assert result["delay"]["completed_ects"] == 0


def test_service_delay_ects_never_negative():
    svc, _ = _make_service(
        _progress_result(completed_ects=200, expected_ects=120, status="AHEAD")
    )
    result = svc.detect_student_delay(1)
    assert result["delay"]["delay_ects"] >= 0


def test_service_result_contains_all_required_fields():
    svc, _ = _make_service()
    result = svc.detect_student_delay(1)
    delay = result["delay"]
    for field in [
        "student_id", "student_number", "student_name", "programme",
        "current_semester", "completed_ects", "expected_ects",
        "is_delayed", "delay_ects", "difference_ects",
    ]:
        assert field in delay, f"Missing field: {field}"


def test_service_completed_ects_from_progress_service():
    svc, progress_svc = _make_service(
        _progress_result(completed_ects=45, expected_ects=90)
    )
    result = svc.detect_student_delay(1)
    assert result["delay"]["completed_ects"] == 45


def test_service_expected_ects_from_progress_service():
    svc, progress_svc = _make_service(
        _progress_result(completed_ects=45, expected_ects=90)
    )
    result = svc.detect_student_delay(1)
    assert result["delay"]["expected_ects"] == 90


def test_service_calls_progress_service_with_student_id():
    svc, progress_svc = _make_service()
    svc.detect_student_delay(42)
    progress_svc.get_progress.assert_called_once_with(42)


def test_service_does_not_call_progress_service_twice():
    """#93 must not recalculate by calling get_progress multiple times."""
    svc, progress_svc = _make_service()
    svc.detect_student_delay(1)
    assert progress_svc.get_progress.call_count == 1


# ── Error propagation ─────────────────────────────────────────────────────────

def test_service_propagates_student_not_found():
    svc, _ = _make_service({
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student not found.",
    })
    result = svc.detect_student_delay(999)
    assert result["success"] is False
    assert result["error"] == "STUDENT_NOT_FOUND"


def test_service_propagates_curriculum_not_found():
    svc, _ = _make_service({
        "success": False,
        "error": "CURRICULUM_NOT_FOUND",
        "message": "Curriculum not found.",
    })
    result = svc.detect_student_delay(1)
    assert result["success"] is False
    assert result["error"] == "CURRICULUM_NOT_FOUND"


def test_service_propagates_invalid_student_id():
    svc, _ = _make_service({
        "success": False,
        "error": "INVALID_STUDENT_ID",
        "message": "Invalid ID.",
    })
    result = svc.detect_student_delay(0)
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


def test_service_missing_data_not_treated_as_not_delayed():
    """A student with missing data must not silently appear as on schedule."""
    svc, _ = _make_service({
        "success": False,
        "error": "CURRICULUM_NOT_FOUND",
        "message": "Missing.",
    })
    result = svc.detect_student_delay(1)
    assert result["success"] is False
    assert "delay" not in result


# ── Multiple programmes ───────────────────────────────────────────────────────

def test_two_students_different_programmes_not_mixed():
    """Results for two students in different programmes must be independent."""
    progress_svc1 = Mock()
    progress_svc1.get_progress.return_value = _progress_result(
        student_id=1, student_number="S001",
        programme="Business IT",
        completed_ects=60, expected_ects=120,
    )
    svc1 = DelayDetectionService(progress_service=progress_svc1)
    result1 = svc1.detect_student_delay(1)

    progress_svc2 = Mock()
    progress_svc2.get_progress.return_value = _progress_result(
        student_id=2, student_number="S002",
        programme="Data Engineering",
        completed_ects=120, expected_ects=120,
        status="ON_TRACK",
    )
    svc2 = DelayDetectionService(progress_service=progress_svc2)
    result2 = svc2.detect_student_delay(2)

    # Student 1 (Business IT) is delayed
    assert result1["delay"]["is_delayed"] is True
    assert result1["delay"]["delay_ects"] == 60
    assert result1["delay"]["programme"] == "Business IT"

    # Student 2 (Data Engineering) is on track
    assert result2["delay"]["is_delayed"] is False
    assert result2["delay"]["delay_ects"] == 0
    assert result2["delay"]["programme"] == "Data Engineering"

    # Results are not mixed
    assert result1["delay"]["student_id"] != result2["delay"]["student_id"]


def test_same_delay_rule_applies_regardless_of_programme():
    """No programme-specific detection branches exist."""
    for programme in ["Business IT", "Data Engineering", "Cybersecurity"]:
        progress_svc = Mock()
        progress_svc.get_progress.return_value = _progress_result(
            programme=programme,
            completed_ects=60,
            expected_ects=120,
        )
        svc = DelayDetectionService(progress_service=progress_svc)
        result = svc.detect_student_delay(1)
        assert result["delay"]["is_delayed"] is True, f"Failed for {programme}"
        assert result["delay"]["delay_ects"] == 60, f"Wrong delay for {programme}"


# ── Result does not contain out-of-scope fields ───────────────────────────────

def test_result_does_not_contain_risk_fields():
    """#93 must not implement #94/#95/#96 functionality."""
    svc, _ = _make_service()
    result = svc.detect_student_delay(1)
    delay = result.get("delay", {})
    forbidden = [
        "risk_level", "risk_score", "academic_health_score",
        "recommendation", "warning_message", "is_at_risk",
    ]
    for field in forbidden:
        assert field not in delay, f"Field '{field}' belongs to a later issue"


# ── Determinism ───────────────────────────────────────────────────────────────

def test_detection_is_deterministic():
    """Same inputs must always produce same result."""
    svc1, _ = _make_service(_progress_result(completed_ects=60, expected_ects=120))
    svc2, _ = _make_service(_progress_result(completed_ects=60, expected_ects=120))
    r1 = svc1.detect_student_delay(1)
    r2 = svc2.detect_student_delay(1)
    assert r1["delay"]["is_delayed"] == r2["delay"]["is_delayed"]
    assert r1["delay"]["delay_ects"] == r2["delay"]["delay_ects"]


# ── #91 and #92 boundary tests ────────────────────────────────────────────────

def test_completed_ects_not_recalculated_by_93():
    """#93 must consume completed_ects from ProgressService, not recalculate."""
    svc, progress_svc = _make_service(
        _progress_result(completed_ects=75, expected_ects=90)
    )
    svc.detect_student_delay(1)
    # Only one call to progress service — no independent SQL
    assert progress_svc.get_progress.call_count == 1
    result = svc.detect_student_delay(1)
    assert result["delay"]["completed_ects"] == 75


def test_expected_ects_not_recalculated_by_93():
    """#93 must consume expected_ects from ProgressService, not recalculate."""
    svc, progress_svc = _make_service(
        _progress_result(completed_ects=75, expected_ects=90)
    )
    result = svc.detect_student_delay(1)
    assert result["delay"]["expected_ects"] == 90
