"""Unit tests for StudentDashboardService — Issue #77."""

from datetime import date
from unittest.mock import Mock, patch

import pytest

from app.services.student_dashboard_service import StudentDashboardService


AS_OF = date(2026, 8, 8)


class _DateMeta(type):
    def __instancecheck__(cls, instance):
        return isinstance(instance, date)


class _TrackingDate(date, metaclass=_DateMeta):
    today = Mock(return_value=AS_OF)


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


def _make_health_result(score=100, level="STRONG", status="COMPLETE"):
    return {
        "success": True,
        "student_id": 1,
        "assessment_status": status,
        "health_score": score,
        "health_level": level,
        "components": [],
        "missing_indicators": [],
        "summary": (
            f"Academic health is {level.lower()} at {score}/100."
            if score is not None and level is not None
            else "Academic health is partial because required indicators are unavailable."
        ),
    }


def _make_risk_result(level="LOW", score=0, status="COMPLETE"):
    return {
        "success": True,
        "student_id": 1,
        "assessment_status": status,
        "score": score,
        "risk_level": level,
        "explanation": [f"Canonical academic risk is {level}."],
        "indicator_contributions": [],
        "unavailable_indicators": [],
        "applied_overrides": [],
        "policy_version": "academic-risk-v1",
    }


def _assert_unavailable_health(value):
    assert value == {
        "success": False,
        "assessment_status": "UNAVAILABLE",
        "health_score": None,
        "health_level": None,
        "components": [],
        "missing_indicators": ["ACADEMIC_HEALTH_SERVICE_UNAVAILABLE"],
        "summary": "Academic health is unavailable.",
    }


def _make_service(
    student_result=None,
    progress_result=None,
    study_right_result=None,
    events_result=None,
    health_result=None,
    risk_result=None,
    health_service=None,
    risk_service=None,
    event_service=None,
    include_canonical=True,
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
    event_svc = event_service or Mock()
    event_svc.get_upcoming_events.return_value = (
        events_result if events_result is not None else _make_events_result()
    )
    health_svc = health_service or Mock()
    if health_service is None or health_result is not None:
        health_svc.convert_risk_assessment.return_value = (
            health_result if health_result is not None else _make_health_result()
        )
    risk_svc = risk_service or Mock()
    if risk_service is None or risk_result is not None:
        risk_svc.assess_student_risk.return_value = (
            risk_result if risk_result is not None else _make_risk_result()
        )
    kwargs = {
        "student_service": student_svc,
        "progress_service": progress_svc,
        "study_right_service": study_right_svc,
        "event_service": event_svc,
        "academic_health_service": health_svc,
    }
    if include_canonical:
        kwargs["academic_risk_service"] = risk_svc
    return StudentDashboardService(
        **kwargs,
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
    assert "academic_health" in dash
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
        progress_result=_make_progress_result("BEHIND", 30, 180),
        risk_result=_make_risk_result("HIGH", 50),
    )
    result = svc.get_student_dashboard(1)
    risk = result["dashboard"]["risk"]
    assert risk["current_analysis"]["risk_level"] == "HIGH"


def test_risk_level_medium_when_expiring_soon() -> None:
    svc = _make_service(
        progress_result=_make_progress_result("ON_TRACK", 120, 120),
        study_right_result=_make_study_right_result("EXPIRES_SOON", expiring=True),
        risk_result=_make_risk_result("MEDIUM", 20),
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
        progress_result=_make_progress_result("BEHIND", 10, 180),
        risk_result=_make_risk_result("HIGH", 50),
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


def test_dashboard_includes_health_service_result_without_mapping_it():
    expected = _make_health_result(61, "STABLE")
    svc = _make_service(health_result=expected)
    result = svc.get_student_dashboard(1)
    assert result["dashboard"]["academic_health"] == expected


def test_dashboard_evaluates_canonical_risk_once_and_converts_same_result():
    canonical = _make_risk_result("HIGH", 50)
    risk_service = Mock()
    risk_service.assess_student_risk.return_value = canonical
    health_service = Mock()
    health_service.convert_risk_assessment.return_value = _make_health_result(
        50, "NEEDS_ATTENTION"
    )
    svc = _make_service(
        risk_service=risk_service,
        health_service=health_service,
    )

    result = svc.get_student_dashboard(1)

    risk_service.assess_student_risk.assert_called_once()
    health_service.convert_risk_assessment.assert_called_once_with(canonical)
    assert health_service.convert_risk_assessment.call_args.args[0] is canonical
    assert result["dashboard"]["risk"]["current_analysis"]["risk_level"] == "HIGH"
    assert result["dashboard"]["academic_health"]["health_score"] == 50


def test_dashboard_uses_one_explicit_date_for_risk_and_events():
    risk_service = Mock()
    risk_service.assess_student_risk.return_value = _make_risk_result()
    event_service = Mock()
    event_service.get_upcoming_events.return_value = _make_events_result()
    svc = _make_service(
        risk_service=risk_service,
        event_service=event_service,
    )

    _TrackingDate.today.reset_mock()
    with patch("app.services.student_dashboard_service.date", _TrackingDate):
        svc.get_student_dashboard(1, as_of_date=AS_OF)

    _TrackingDate.today.assert_not_called()
    risk_service.assess_student_risk.assert_called_once_with(
        1, as_of_date=AS_OF, allow_partial_risk_level=False
    )
    event_service.get_upcoming_events.assert_called_once_with(
        start_date=AS_OF.isoformat(), end_date=None
    )


def test_dashboard_captures_default_date_once_and_reuses_it():
    first = date(2026, 8, 8)
    second = date(2026, 8, 9)
    risk_service = Mock()
    risk_service.assess_student_risk.return_value = _make_risk_result()
    event_service = Mock()
    event_service.get_upcoming_events.return_value = _make_events_result()
    svc = _make_service(risk_service=risk_service, event_service=event_service)
    _TrackingDate.today.reset_mock()
    _TrackingDate.today.side_effect = [first, second]

    with patch("app.services.student_dashboard_service.date", _TrackingDate):
        svc.get_student_dashboard(1)

    _TrackingDate.today.assert_called_once_with()
    risk_service.assess_student_risk.assert_called_once_with(
        1, as_of_date=first, allow_partial_risk_level=False
    )
    event_service.get_upcoming_events.assert_called_once_with(
        start_date=first.isoformat(), end_date=None
    )
    _TrackingDate.today.side_effect = None


def test_legacy_low_cannot_replace_more_severe_canonical_risk():
    result = _make_service(
        progress_result=_make_progress_result("ON_TRACK", 120, 120),
        risk_result=_make_risk_result("HIGH", 50),
        health_result=_make_health_result(50, "NEEDS_ATTENTION"),
    ).get_student_dashboard(1)["dashboard"]

    assert result["risk"]["current_analysis"]["risk_level"] == "HIGH"
    assert result["risk"]["supporting_legacy_analysis"]["risk_level"] == "LOW"
    assert result["risk"]["supporting_legacy_analysis"]["authoritative_overall_risk"] is False


def test_constructor_fallback_is_explicitly_noncanonical_and_health_is_unavailable():
    health_service = Mock()
    result = _make_service(
        include_canonical=False, health_service=health_service
    ).get_student_dashboard(
        1, as_of_date=AS_OF
    )["dashboard"]

    current = result["risk"]["current_analysis"]
    assert current == {
        "risk_level": None,
        "reasons": ["Canonical academic risk is unavailable."],
        "assessment_status": "UNAVAILABLE",
        "score": None,
        "source": "LEGACY_PROGRESS_STUDY_RIGHT_FALLBACK",
    }
    supporting = result["risk"]["supporting_legacy_analysis"]
    assert supporting["source"] == "LEGACY_PROGRESS_STUDY_RIGHT_HEURISTIC"
    assert supporting["risk_level"] == "LOW"
    assert supporting["reasons"] == ["No immediate risks detected."]
    assert supporting["reasons"][0] not in current["reasons"]
    assert supporting["authoritative_overall_risk"] is False
    _assert_unavailable_health(result["academic_health"])
    health_service.convert_risk_assessment.assert_not_called()
    assert result["summary"]["priority"] == "UNKNOWN"
    assert result["summary"]["attention_required"] is True
    assert any("unavailable" in item and "indeterminate" in item
               for item in result["summary"]["key_findings"])


def test_canonical_risk_exception_degrades_to_explicit_fallback():
    risk_service = Mock()
    risk_service.assess_student_risk.side_effect = RuntimeError("temporary")
    health_service = Mock()

    result = _make_service(
        risk_service=risk_service, health_service=health_service
    ).get_student_dashboard(
        1, as_of_date=AS_OF
    )

    assert result["success"] is True
    current = result["dashboard"]["risk"]["current_analysis"]
    assert current["source"] == "LEGACY_PROGRESS_STUDY_RIGHT_FALLBACK"
    assert current["risk_level"] is None
    assert current["score"] is None
    _assert_unavailable_health(result["dashboard"]["academic_health"])
    health_service.convert_risk_assessment.assert_not_called()


def test_returned_canonical_failure_is_not_converted_and_health_is_unavailable():
    risk_service = Mock()
    risk_service.assess_student_risk.return_value = {
        "success": False,
        "assessment_status": "UNPROCESSABLE",
        "error": "RISK_EVIDENCE_FAILURE",
    }
    health_service = Mock()
    svc = _make_service(risk_service=risk_service, health_service=health_service)

    dashboard = svc.get_student_dashboard(1, as_of_date=AS_OF)["dashboard"]

    health_service.convert_risk_assessment.assert_not_called()
    _assert_unavailable_health(dashboard["academic_health"])
    assert dashboard["risk"]["current_analysis"]["assessment_status"] == "UNAVAILABLE"


def test_all_canonical_risk_levels_map_to_dashboard_priority():
    expected = {
        "CRITICAL": (70, "HIGH", True),
        "HIGH": (40, "HIGH", True),
        "MEDIUM": (20, "MEDIUM", True),
        "LOW": (0, "LOW", False),
    }
    for level, (score, priority, attention_required) in expected.items():
        dashboard = _make_service(
            risk_result=_make_risk_result(level, score)
        ).get_student_dashboard(1, as_of_date=AS_OF)["dashboard"]
        assert dashboard["summary"]["priority"] == priority
        assert dashboard["summary"]["attention_required"] is attention_required


def test_partial_risk_has_indeterminate_summary_without_using_legacy_level():
    dashboard = _make_service(
        risk_result=_make_risk_result(None, None, "PARTIAL"),
        health_result=_make_health_result(None, None, "PARTIAL"),
    ).get_student_dashboard(1, as_of_date=AS_OF)["dashboard"]

    assert dashboard["risk"]["current_analysis"]["risk_level"] is None
    assert dashboard["risk"]["supporting_legacy_analysis"]["risk_level"] == "LOW"
    assert dashboard["risk"]["supporting_legacy_analysis"]["authoritative_overall_risk"] is False
    assert dashboard["academic_health"]["health_score"] is None
    assert dashboard["academic_health"]["health_level"] is None
    assert dashboard["summary"]["priority"] == "UNKNOWN"
    assert dashboard["summary"]["attention_required"] is True
    assert any("incomplete" in item and "indeterminate" in item
               for item in dashboard["summary"]["key_findings"])


def test_unsupported_risk_level_has_indeterminate_summary():
    dashboard = _make_service(
        risk_result=_make_risk_result("EXTREME", 70)
    ).get_student_dashboard(1, as_of_date=AS_OF)["dashboard"]

    assert dashboard["summary"]["priority"] == "UNKNOWN"
    assert dashboard["summary"]["attention_required"] is True
    assert any("unsupported" in item and "indeterminate" in item
               for item in dashboard["summary"]["key_findings"])


def test_expired_study_right_dashboard_is_consistent_with_canonical_health():
    dashboard = _make_service(
        study_right_result=_make_study_right_result("EXPIRED"),
        risk_result=_make_risk_result("CRITICAL", 70),
        health_result=_make_health_result(30, "URGENT_SUPPORT"),
    ).get_student_dashboard(1, as_of_date=AS_OF)["dashboard"]

    assert dashboard["risk"]["current_analysis"]["score"] == 70
    assert dashboard["risk"]["current_analysis"]["risk_level"] == "CRITICAL"
    assert dashboard["academic_health"]["health_score"] == 30
    assert dashboard["academic_health"]["health_level"] == "URGENT_SUPPORT"
    assert dashboard["summary"]["priority"] == "HIGH"
    assert dashboard["summary"]["attention_required"] is True


def test_dashboard_preserves_existing_sections_with_health_integration():
    result = _make_service().get_student_dashboard(1)["dashboard"]
    assert set(result) == {
        "profile", "academic_progress", "study_right", "academic_health",
        "risk", "upcoming_actions", "summary",
    }


def test_health_service_failure_degrades_without_losing_dashboard():
    health_service = Mock()
    health_service.convert_risk_assessment.side_effect = RuntimeError("down")
    svc = _make_service(health_service=health_service)
    result = svc.get_student_dashboard(1)
    assert result["success"] is True
    assert result["dashboard"]["academic_health"]["health_score"] is None
    assert result["dashboard"]["academic_health"]["missing_indicators"] == [
        "ACADEMIC_HEALTH_SERVICE_FAILURE"
    ]


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
