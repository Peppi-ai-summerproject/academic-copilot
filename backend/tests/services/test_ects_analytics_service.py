"""Unit tests for EctsAnalyticsService — Issue #91."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.services.ects_analytics_service import EctsAnalyticsService, _build_cohort_summary


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_service(progress_result=None):
    """Create EctsAnalyticsService with a mocked ProgressService."""
    progress_svc = Mock()
    progress_svc.get_progress.return_value = (
        progress_result if progress_result is not None
        else _on_track_result()
    )
    return EctsAnalyticsService(progress_service=progress_svc), progress_svc


def _progress_data(
    completed=120,
    expected=120,
    status="ON_TRACK",
    semester=4,
    programme="Business IT",
):
    diff = completed - expected
    return {
        "success": True,
        "progress": {
            "student_id": 1,
            "student_number": "S001",
            "student_name": "Mikael Virtanen",
            "programme": programme,
            "current_semester": semester,
            "completed_ects": completed,
            "expected_ects": expected,
            "difference_ects": diff,
            "remaining_to_expected_ects": max(expected - completed, 0),
            "progress_percentage": round((completed / expected * 100), 2) if expected else 0.0,
            "status": status,
        },
    }


def _on_track_result():
    return _progress_data(120, 120, "ON_TRACK")


def _behind_result():
    return _progress_data(60, 120, "BEHIND")


def _ahead_result():
    return _progress_data(150, 120, "AHEAD")


# ── calculate_ects_progress — success cases ───────────────────────────────────

def test_returns_success_true_for_valid_student():
    svc, _ = _make_service(_on_track_result())
    result = svc.calculate_ects_progress(1)
    assert result["success"] is True


def test_returns_analytics_section():
    svc, _ = _make_service(_on_track_result())
    result = svc.calculate_ects_progress(1)
    assert "analytics" in result


def test_analytics_contains_completed_ects():
    svc, _ = _make_service(_on_track_result())
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["completed_ects"] == 120


def test_analytics_contains_expected_ects():
    svc, _ = _make_service(_on_track_result())
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["expected_ects"] == 120


def test_analytics_on_track_flags():
    svc, _ = _make_service(_on_track_result())
    result = svc.calculate_ects_progress(1)
    analytics = result["analytics"]
    assert analytics["is_on_track"] is True
    assert analytics["is_behind"] is False
    assert analytics["is_ahead"] is False
    assert analytics["progress_status"] == "ON_TRACK"


def test_analytics_behind_flags():
    svc, _ = _make_service(_behind_result())
    result = svc.calculate_ects_progress(1)
    analytics = result["analytics"]
    assert analytics["is_behind"] is True
    assert analytics["is_on_track"] is False
    assert analytics["is_ahead"] is False
    assert analytics["progress_status"] == "BEHIND"


def test_analytics_ahead_flags():
    svc, _ = _make_service(_ahead_result())
    result = svc.calculate_ects_progress(1)
    analytics = result["analytics"]
    assert analytics["is_ahead"] is True
    assert analytics["is_on_track"] is False
    assert analytics["is_behind"] is False
    assert analytics["progress_status"] == "AHEAD"


def test_ects_to_graduate_calculated_correctly():
    svc, _ = _make_service(_progress_data(completed=120))
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["ects_to_graduate"] == 120


def test_ects_to_graduate_zero_when_completed():
    svc, _ = _make_service(_progress_data(completed=240))
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["ects_to_graduate"] == 0


def test_ects_to_graduate_not_negative():
    svc, _ = _make_service(_progress_data(completed=300))
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["ects_to_graduate"] == 0


def test_total_required_ects_is_240():
    svc, _ = _make_service()
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["total_required_ects"] == 240


def test_student_number_in_analytics():
    svc, _ = _make_service()
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["student_number"] == "S001"


def test_student_name_in_analytics():
    svc, _ = _make_service()
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["student_name"] == "Mikael Virtanen"


def test_programme_in_analytics():
    svc, _ = _make_service()
    result = svc.calculate_ects_progress(1)
    assert result["analytics"]["programme"] == "Business IT"


def test_progress_service_called_with_student_id():
    svc, progress_svc = _make_service()
    svc.calculate_ects_progress(42)
    progress_svc.get_progress.assert_called_once_with(42)


def test_analytics_has_all_required_fields():
    svc, _ = _make_service()
    result = svc.calculate_ects_progress(1)
    analytics = result["analytics"]
    required_fields = [
        "student_id", "student_number", "student_name", "programme",
        "current_semester", "completed_ects", "expected_ects",
        "difference_ects", "progress_percentage", "progress_status",
        "is_behind", "is_on_track", "is_ahead",
        "ects_to_graduate", "total_required_ects",
    ]
    for field in required_fields:
        assert field in analytics, f"Missing field: {field}"


# ── calculate_ects_progress — error cases ─────────────────────────────────────

def test_returns_error_when_student_not_found():
    svc, _ = _make_service({
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student not found.",
    })
    result = svc.calculate_ects_progress(999)
    assert result["success"] is False
    assert result["error"] == "STUDENT_NOT_FOUND"


def test_returns_error_when_curriculum_not_found():
    svc, _ = _make_service({
        "success": False,
        "error": "CURRICULUM_NOT_FOUND",
        "message": "Curriculum not found.",
    })
    result = svc.calculate_ects_progress(1)
    assert result["success"] is False
    assert result["error"] == "CURRICULUM_NOT_FOUND"


def test_returns_error_when_invalid_student_id():
    svc, _ = _make_service({
        "success": False,
        "error": "INVALID_STUDENT_ID",
        "message": "Student ID must be a positive integer.",
    })
    result = svc.calculate_ects_progress(0)
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


def test_propagates_progress_service_error_intact():
    error_result = {
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Connection failed.",
    }
    svc, _ = _make_service(error_result)
    result = svc.calculate_ects_progress(1)
    assert result == error_result


# ── calculate_ects_for_cohort ─────────────────────────────────────────────────

def test_cohort_empty_list_returns_error():
    svc, _ = _make_service()
    result = svc.calculate_ects_for_cohort([])
    assert result["success"] is False
    assert result["error"] == "EMPTY_STUDENT_LIST"


def test_cohort_single_student_success():
    svc, _ = _make_service(_on_track_result())
    result = svc.calculate_ects_for_cohort([1])
    assert result["success"] is True
    assert result["processed"] == 1
    assert result["failed"] == 0
    assert len(result["results"]) == 1


def test_cohort_multiple_students():
    progress_svc = Mock()
    progress_svc.get_progress.return_value = _on_track_result()
    svc = EctsAnalyticsService(progress_service=progress_svc)
    result = svc.calculate_ects_for_cohort([1, 2, 3])
    assert result["processed"] == 3
    assert result["failed"] == 0


def test_cohort_partial_failure():
    progress_svc = Mock()
    progress_svc.get_progress.side_effect = [
        _on_track_result(),
        {"success": False, "error": "STUDENT_NOT_FOUND", "message": "Not found."},
        _behind_result(),
    ]
    svc = EctsAnalyticsService(progress_service=progress_svc)
    result = svc.calculate_ects_for_cohort([1, 2, 3])
    assert result["processed"] == 2
    assert result["failed"] == 1
    assert len(result["errors"]) == 1


def test_cohort_all_fail_returns_success_false():
    svc, _ = _make_service({
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Not found.",
    })
    result = svc.calculate_ects_for_cohort([1, 2])
    assert result["success"] is False
    assert result["processed"] == 0
    assert result["failed"] == 2


def test_cohort_summary_contains_counts():
    progress_svc = Mock()
    progress_svc.get_progress.side_effect = [
        _on_track_result(),
        _behind_result(),
        _ahead_result(),
    ]
    svc = EctsAnalyticsService(progress_service=progress_svc)
    result = svc.calculate_ects_for_cohort([1, 2, 3])
    summary = result["summary"]
    assert summary["total_students"] == 3
    assert summary["on_track_count"] == 1
    assert summary["behind_count"] == 1
    assert summary["ahead_count"] == 1


def test_cohort_summary_average_ects():
    progress_svc = Mock()
    progress_svc.get_progress.side_effect = [
        _progress_data(completed=60),
        _progress_data(completed=120),
    ]
    svc = EctsAnalyticsService(progress_service=progress_svc)
    result = svc.calculate_ects_for_cohort([1, 2])
    assert result["summary"]["average_completed_ects"] == 90.0


def test_cohort_errors_contain_student_id():
    progress_svc = Mock()
    progress_svc.get_progress.return_value = {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Not found.",
    }
    svc = EctsAnalyticsService(progress_service=progress_svc)
    result = svc.calculate_ects_for_cohort([999])
    assert result["errors"][0]["student_id"] == 999


# ── _build_cohort_summary ─────────────────────────────────────────────────────

def test_build_cohort_summary_empty():
    summary = _build_cohort_summary([])
    assert summary["total_students"] == 0
    assert summary["average_completed_ects"] == 0.0


def test_build_cohort_summary_counts():
    analytics = [
        {"is_behind": True, "is_on_track": False, "is_ahead": False,
         "completed_ects": 60, "progress_percentage": 50.0},
        {"is_behind": False, "is_on_track": True, "is_ahead": False,
         "completed_ects": 120, "progress_percentage": 100.0},
        {"is_behind": False, "is_on_track": False, "is_ahead": True,
         "completed_ects": 150, "progress_percentage": 125.0},
    ]
    summary = _build_cohort_summary(analytics)
    assert summary["total_students"] == 3
    assert summary["behind_count"] == 1
    assert summary["on_track_count"] == 1
    assert summary["ahead_count"] == 1
    assert summary["average_completed_ects"] == 110.0
