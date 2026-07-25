"""Unit tests for StudentDashboardService — Issue #77."""

from datetime import date
from unittest.mock import Mock

import pytest

from app.services.student_dashboard_service import StudentDashboardService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_student_result(student_id=1):
    return {
        "success": True,
        "student": {
            "id": student_id,
            "student_number": "S001",
            "name": "Mikael Virtanen",
            "group_name": "TT21A",
            "programme": "Business IT",
            "programme_code": "DIN2024S",
            "start_date": date(2021, 9, 1),
            "status": "ACTIVE",
        },
    }


def _make_progress_result(status="ON_TRACK", completed=120, expected=120):
    diff = completed - expected
    return {
        "success": True,
        "progress": {
            "student_id": 1,
            "student_number": "S001",
            "student_name": "Mikael Virtanen",
            "programme": "Business IT",
            "current_semester": 4,
            "completed_ects": completed,
            "expected_ects": expected,
            "difference_ects": diff,
            "remaining_to_expected_ects": max(expected - completed, 0),
            "progress_percentage": round((completed / expected) * 100, 2) if expected else 0.0,
            "status": status,
        },
    }


def _make_study_right_result(status="ACTIVE", expiring=False):
    return {
        "success": True,
        "study_right": {
            "id": 1,
            "student_id": 1,
            "start_date": date(2021, 9, 1),
            "end_date": date(2028, 5, 31),
            "status": status,
            "extension_count": 0,
            "expiration_date": date(2028, 5, 31),
            "is_expiring_soon": expiring,
        },
    }


def _make_events_result(events=None):
    return {
        "success": True,
        "filters": {"start_date": "2026-01-01", "end_date": None},
        "event_count": len(events or []),
        "events": events or [],
    }


def _make_service(
    student_result=None,
    progress_result=None,
    study_right_result=None,
    events_result=None,
):
    student_svc = Mock()
    student_svc.get_student.return_value = (
        student_result if student_result is not None else _make_student_result()
    )
    progress_svc = Mock()
    progress_svc.get_progress.return_value = (
        progress_result if progress_result is not None else _make_progress_result()
    )
    study_right_svc = Mock()
    study_right_svc.get_study_right.return_value = (
        study_right_result if study_right_result is not None else _make_study_right_result()
    )
    event_svc = Mock()
    event_svc.get_upcoming_events.return_value = (
        events_result if events_result is not None else _make_events_result()
    )
    return StudentDashboardService(
        student_service=student_svc,
        progress_service=progress_svc,
        study_right_service=study_right_svc,
        event_service=event_svc,
    )


# ── Input validation ──────────────────────────────────────────────────────────

def test_invalid_student_id_zero_returns_error() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(0)
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


def test_invalid_student_id_negative_returns_error() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(-1)
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


# ── Student not found ─────────────────────────────────────────────────────────

def test_missing_student_returns_not_found_error() -> None:
    svc = _make_service(
        student_result={"success": False, "error": "STUDENT_NOT_FOUND",
                        "message": "Not found."}
    )
    result = svc.get_student_dashboard(999)
    assert result["success"] is False
    assert result["error"] == "STUDENT_NOT_FOUND"


# ── Complete dashboard ────────────────────────────────────────────────────────

def test_complete_dashboard_has_all_sections() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    assert result["success"] is True
    assert "dashboard" in result
    dash = result["dashboard"]
    assert "profile" in dash
    assert "academic_progress" in dash
    assert "study_right" in dash
    assert "risk" in dash
    assert "upcoming_actions" in dash
    assert "summary" in dash


def test_profile_section_contains_expected_fields() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    profile = result["dashboard"]["profile"]
    assert profile["student_number"] == "S001"
    assert profile["name"] == "Mikael Virtanen"
    assert profile["programme"] == "Business IT"
    assert profile["status"] == "ACTIVE"


def test_profile_start_date_is_serialized_as_string() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    start_date = result["dashboard"]["profile"]["start_date"]
    assert isinstance(start_date, str)


def test_progress_section_available_on_success() -> None:
    svc = _make_service(progress_result=_make_progress_result("ON_TRACK", 120, 120))
    result = svc.get_student_dashboard(1)
    progress = result["dashboard"]["academic_progress"]
    assert progress.get("available") is True
    assert progress["completed_ects"] == 120
    assert progress["status"] == "ON_TRACK"


def test_study_right_section_available_on_success() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    sr = result["dashboard"]["study_right"]
    assert sr.get("available") is True
    assert sr["status"] == "ACTIVE"
    assert isinstance(sr["end_date"], str)


def test_study_right_dates_are_strings() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    sr = result["dashboard"]["study_right"]
    assert isinstance(sr["start_date"], str)
    assert isinstance(sr["end_date"], str)


# ── Graceful degradation ──────────────────────────────────────────────────────

def test_missing_progress_degrades_gracefully() -> None:
    svc = _make_service(
        progress_result={"success": False, "error": "CURRICULUM_NOT_FOUND",
                         "message": "No curriculum."}
    )
    result = svc.get_student_dashboard(1)
    assert result["success"] is True
    progress = result["dashboard"]["academic_progress"]
    assert progress.get("available") is False
    assert progress["reason"] == "CURRICULUM_NOT_FOUND"


def test_missing_study_right_degrades_gracefully() -> None:
    svc = _make_service(
        study_right_result={"success": False, "error": "STUDY_RIGHT_NOT_FOUND",
                            "message": "Not found."}
    )
    result = svc.get_student_dashboard(1)
    assert result["success"] is True
    sr = result["dashboard"]["study_right"]
    assert sr.get("available") is False
    assert sr["reason"] == "STUDY_RIGHT_NOT_FOUND"


def test_no_upcoming_events_returns_empty_lists() -> None:
    svc = _make_service(events_result=_make_events_result([]))
    result = svc.get_student_dashboard(1)
    actions = result["dashboard"]["upcoming_actions"]
    assert actions["academic_events"] == []
    assert actions["tutor_meetings"] == []
    assert actions["recommended_actions"] == []


def test_upcoming_actions_never_none() -> None:
    svc = _make_service(
        events_result={"success": False, "error": "DB_ERROR", "message": "fail"}
    )
    result = svc.get_student_dashboard(1)
    actions = result["dashboard"]["upcoming_actions"]
    assert isinstance(actions["academic_events"], list)
    assert isinstance(actions["tutor_meetings"], list)
    assert isinstance(actions["recommended_actions"], list)


# ── Risk section ──────────────────────────────────────────────────────────────

def test_risk_events_list_is_empty_when_no_repository() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    assert result["dashboard"]["risk"]["events"] == []


def test_risk_level_high_when_far_behind() -> None:
    svc = _make_service(
        progress_result=_make_progress_result("BEHIND", 30, 180)
    )
    result = svc.get_student_dashboard(1)
    risk = result["dashboard"]["risk"]
    assert risk["current_analysis"]["risk_level"] == "HIGH"


def test_risk_level_medium_when_expiring_soon() -> None:
    svc = _make_service(
        progress_result=_make_progress_result("ON_TRACK", 120, 120),
        study_right_result=_make_study_right_result("EXPIRES_SOON", expiring=True),
    )
    result = svc.get_student_dashboard(1)
    risk = result["dashboard"]["risk"]
    assert risk["current_analysis"]["risk_level"] in ("MEDIUM", "HIGH")


def test_risk_level_low_for_healthy_student() -> None:
    svc = _make_service(
        progress_result=_make_progress_result("ON_TRACK", 120, 120),
        study_right_result=_make_study_right_result("ACTIVE"),
    )
    result = svc.get_student_dashboard(1)
    assert result["dashboard"]["risk"]["current_analysis"]["risk_level"] == "LOW"


# ── Summary section ───────────────────────────────────────────────────────────

def test_summary_attention_required_when_behind() -> None:
    svc = _make_service(
        progress_result=_make_progress_result("BEHIND", 60, 120)
    )
    result = svc.get_student_dashboard(1)
    summary = result["dashboard"]["summary"]
    assert summary["attention_required"] is True
    assert summary["overall_status"] == "NEEDS_ATTENTION"


def test_summary_no_attention_for_healthy_student() -> None:
    svc = _make_service(
        progress_result=_make_progress_result("ON_TRACK", 120, 120),
        study_right_result=_make_study_right_result("ACTIVE"),
    )
    result = svc.get_student_dashboard(1)
    summary = result["dashboard"]["summary"]
    assert summary["attention_required"] is False
    assert summary["overall_status"] == "ON_TRACK"


def test_summary_key_findings_is_list() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    assert isinstance(result["dashboard"]["summary"]["key_findings"], list)
    assert len(result["dashboard"]["summary"]["key_findings"]) > 0


def test_summary_priority_high_for_high_risk() -> None:
    svc = _make_service(
        progress_result=_make_progress_result("BEHIND", 10, 180)
    )
    result = svc.get_student_dashboard(1)
    assert result["dashboard"]["summary"]["priority"] == "HIGH"


def test_summary_priority_low_for_healthy_student() -> None:
    svc = _make_service(
        progress_result=_make_progress_result("ON_TRACK", 120, 120),
        study_right_result=_make_study_right_result("ACTIVE"),
    )
    result = svc.get_student_dashboard(1)
    assert result["dashboard"]["summary"]["priority"] == "LOW"


# ── Response serialization ────────────────────────────────────────────────────

def test_response_is_json_serializable() -> None:
    import json
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    # Should not raise
    json.dumps(result)


def test_student_id_in_response() -> None:
    svc = _make_service()
    result = svc.get_student_dashboard(1)
    assert result["student_id"] == 1


# ── Service reuse verification ────────────────────────────────────────────────

def test_student_service_is_called_with_correct_id() -> None:
    student_svc = Mock()
    student_svc.get_student.return_value = {"success": False,
                                             "error": "STUDENT_NOT_FOUND",
                                             "message": "Not found."}
    svc = StudentDashboardService(
        student_service=student_svc,
        progress_service=Mock(),
        study_right_service=Mock(),
        event_service=Mock(),
    )
    svc.get_student_dashboard(42)
    student_svc.get_student.assert_called_once_with(42)


def test_progress_service_not_called_when_student_missing() -> None:
    student_svc = Mock()
    student_svc.get_student.return_value = {"success": False,
                                             "error": "STUDENT_NOT_FOUND",
                                             "message": "Not found."}
    progress_svc = Mock()
    svc = StudentDashboardService(
        student_service=student_svc,
        progress_service=progress_svc,
        study_right_service=Mock(),
        event_service=Mock(),
    )
    svc.get_student_dashboard(999)
    progress_svc.get_progress.assert_not_called()
