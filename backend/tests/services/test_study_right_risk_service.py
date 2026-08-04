"""Unit tests for StudyRightRiskService — Issue #94.

All tests use fixed dates. No live database, LLM, or network required.

Detection rules (confirmed from risk_policy.py and study_rights table):
    Status-based (authoritative):
        EXPIRED       → risk_status=EXPIRED,       requires_attention=True
        EXPIRES_SOON  → risk_status=EXPIRING_SOON, requires_attention=True
        EXTENDED      → risk_status=EXTENDED,      requires_attention=True
        ACTIVE        → risk_status=SAFE,           requires_attention=False
        GRADUATED     → risk_status=SAFE,           requires_attention=False

    Date-based (supporting evidence):
        days_until_expiration = end_date - as_of_date
        Negative = already expired.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock

import pytest

from app.services.study_right_risk_service import (
    ALERT_CODE_EXPIRED,
    ALERT_CODE_EXPIRING_SOON,
    ALERT_CODE_EXTENDED,
    RISK_STATUS_EXPIRED,
    RISK_STATUS_EXPIRING_SOON,
    RISK_STATUS_EXTENDED,
    RISK_STATUS_SAFE,
    RISK_STATUS_UNKNOWN,
    StudyRightRiskService,
    analyze_study_right_expiration,
    classify_study_right_risk,
)

# ── Fixed reference date for deterministic tests ──────────────────────────────
AS_OF = date(2026, 1, 15)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _study_right(
    sr_id=1,
    status="ACTIVE",
    end_date=date(2028, 5, 31),
    extension_count=0,
):
    return {
        "success": True,
        "study_right": {
            "id": sr_id,
            "student_id": 1,
            "start_date": date(2021, 9, 1),
            "end_date": end_date,
            "status": status,
            "extension_count": extension_count,
            "expiration_date": end_date,
            "is_expiring_soon": status == "EXPIRES_SOON",
        },
    }


def _student(student_id=1, name="Mikael Virtanen", programme="Business IT"):
    return {
        "success": True,
        "student": {
            "id": student_id,
            "student_number": "S001",
            "name": name,
            "programme": programme,
            "status": "ACTIVE",
        },
    }


def _make_service(study_right_result=None, student_result=None):
    sr_svc = Mock()
    sr_svc.get_study_right.return_value = (
        study_right_result if study_right_result is not None
        else _study_right()
    )
    student_svc = Mock()
    student_svc.get_student.return_value = (
        student_result if student_result is not None
        else _student()
    )
    return StudyRightRiskService(
        study_right_service=sr_svc,
        student_service=student_svc,
    ), sr_svc, student_svc


# ── analyze_study_right_expiration tests ──────────────────────────────────────

def test_expired_end_date_gives_negative_days():
    result = analyze_study_right_expiration(
        end_date=date(2025, 1, 1),
        as_of_date=AS_OF,
    )
    assert result["days_until_expiration"] < 0
    assert result["is_date_expired"] is True
    assert result["is_date_expiring_today"] is False


def test_today_end_date_gives_zero_days():
    result = analyze_study_right_expiration(
        end_date=AS_OF,
        as_of_date=AS_OF,
    )
    assert result["days_until_expiration"] == 0
    assert result["is_date_expiring_today"] is True
    assert result["is_date_expired"] is False


def test_future_end_date_gives_positive_days():
    result = analyze_study_right_expiration(
        end_date=date(2028, 5, 31),
        as_of_date=AS_OF,
    )
    assert result["days_until_expiration"] > 0
    assert result["is_date_expired"] is False
    assert result["is_date_expiring_today"] is False


def test_exact_days_calculation():
    end = date(2026, 2, 14)  # 30 days after AS_OF (Jan 15)
    result = analyze_study_right_expiration(end_date=end, as_of_date=AS_OF)
    assert result["days_until_expiration"] == 30


def test_missing_end_date_returns_no_date():
    result = analyze_study_right_expiration(end_date=None, as_of_date=AS_OF)
    assert result["has_end_date"] is False
    assert result["days_until_expiration"] is None
    assert result["is_date_expired"] is False
    assert result["is_date_expiring_today"] is False


def test_has_end_date_true_when_present():
    result = analyze_study_right_expiration(
        end_date=date(2028, 5, 31), as_of_date=AS_OF
    )
    assert result["has_end_date"] is True


def test_is_deterministic():
    r1 = analyze_study_right_expiration(date(2027, 1, 1), AS_OF)
    r2 = analyze_study_right_expiration(date(2027, 1, 1), AS_OF)
    assert r1 == r2


# ── classify_study_right_risk tests ──────────────────────────────────────────

def _date_analysis(days=365):
    return {
        "has_end_date": True,
        "days_until_expiration": days,
        "is_date_expired": days < 0,
        "is_date_expiring_today": days == 0,
    }


def test_expired_status_gives_expired_risk():
    result = classify_study_right_risk("EXPIRED", _date_analysis(-30))
    assert result["risk_status"] == RISK_STATUS_EXPIRED
    assert result["requires_attention"] is True
    assert result["alert_code"] == ALERT_CODE_EXPIRED


def test_expires_soon_gives_expiring_soon_risk():
    result = classify_study_right_risk("EXPIRES_SOON", _date_analysis(60))
    assert result["risk_status"] == RISK_STATUS_EXPIRING_SOON
    assert result["requires_attention"] is True
    assert result["alert_code"] == ALERT_CODE_EXPIRING_SOON


def test_extended_gives_extended_risk():
    result = classify_study_right_risk("EXTENDED", _date_analysis(200))
    assert result["risk_status"] == RISK_STATUS_EXTENDED
    assert result["requires_attention"] is True
    assert result["alert_code"] == ALERT_CODE_EXTENDED


def test_active_gives_safe():
    result = classify_study_right_risk("ACTIVE", _date_analysis(730))
    assert result["risk_status"] == RISK_STATUS_SAFE
    assert result["requires_attention"] is False
    assert result["alert_code"] is None


def test_graduated_gives_safe():
    result = classify_study_right_risk("GRADUATED", _date_analysis(0))
    assert result["risk_status"] == RISK_STATUS_SAFE
    assert result["requires_attention"] is False


def test_unknown_status_gives_unknown():
    result = classify_study_right_risk("SOMETHING_NEW", _date_analysis(100))
    assert result["risk_status"] == RISK_STATUS_UNKNOWN
    assert result["requires_attention"] is False
    assert result["alert_code"] is None


def test_none_status_gives_unknown():
    result = classify_study_right_risk(None, _date_analysis(100))
    assert result["risk_status"] == RISK_STATUS_UNKNOWN


def test_expired_alert_message_contains_overdue_days():
    result = classify_study_right_risk("EXPIRED", _date_analysis(-45))
    assert "45" in result["alert_message"]


def test_expires_soon_alert_message_contains_days_remaining():
    result = classify_study_right_risk("EXPIRES_SOON", _date_analysis(30))
    assert "30" in result["alert_message"]


def test_no_alert_for_safe_student():
    result = classify_study_right_risk("ACTIVE", _date_analysis(730))
    assert result["alert_code"] is None


# ── StudyRightRiskService tests ───────────────────────────────────────────────

def test_invalid_student_id_returns_error():
    svc, _, _ = _make_service()
    result = svc.detect_study_right_risk(0, AS_OF)
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


def test_negative_student_id_returns_error():
    svc, _, _ = _make_service()
    result = svc.detect_study_right_risk(-1, AS_OF)
    assert result["success"] is False
    assert result["error"] == "INVALID_STUDENT_ID"


def test_missing_student_propagates_error():
    svc, _, _ = _make_service(
        student_result={
            "success": False,
            "error": "STUDENT_NOT_FOUND",
            "message": "Not found.",
        }
    )
    result = svc.detect_study_right_risk(999, AS_OF)
    assert result["success"] is False
    assert result["error"] == "STUDENT_NOT_FOUND"


def test_active_study_right_is_safe():
    svc, _, _ = _make_service(_study_right(status="ACTIVE", end_date=date(2028, 5, 31)))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["success"] is True
    assert result["risk"]["risk_status"] == RISK_STATUS_SAFE
    assert result["risk"]["requires_attention"] is False
    assert result["risk"]["alert"] is None


def test_expired_study_right_detected():
    svc, _, _ = _make_service(_study_right(status="EXPIRED", end_date=date(2024, 1, 1)))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["risk_status"] == RISK_STATUS_EXPIRED
    assert result["risk"]["requires_attention"] is True
    assert result["risk"]["alert_code"] == ALERT_CODE_EXPIRED


def test_expires_soon_study_right_detected():
    svc, _, _ = _make_service(_study_right(status="EXPIRES_SOON", end_date=date(2026, 3, 1)))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["risk_status"] == RISK_STATUS_EXPIRING_SOON
    assert result["risk"]["requires_attention"] is True
    assert result["risk"]["alert_code"] == ALERT_CODE_EXPIRING_SOON


def test_extended_study_right_detected():
    svc, _, _ = _make_service(_study_right(status="EXTENDED", end_date=date(2027, 5, 31), extension_count=1))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["risk_status"] == RISK_STATUS_EXTENDED
    assert result["risk"]["requires_attention"] is True
    assert result["risk"]["extension_count"] == 1


def test_graduated_study_right_is_safe():
    svc, _, _ = _make_service(_study_right(status="GRADUATED", end_date=date(2025, 5, 31)))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["risk_status"] == RISK_STATUS_SAFE
    assert result["risk"]["requires_attention"] is False


def test_days_until_expiration_calculated():
    end = date(2026, 2, 14)  # 30 days from AS_OF
    svc, _, _ = _make_service(_study_right(status="EXPIRES_SOON", end_date=end))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["days_until_expiration"] == 30


def test_days_until_expiration_negative_for_expired():
    end = date(2024, 1, 1)
    svc, _, _ = _make_service(_study_right(status="EXPIRED", end_date=end))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["days_until_expiration"] < 0
    assert result["risk"]["is_date_expired"] is True


def test_expires_today_detected():
    svc, _, _ = _make_service(_study_right(status="EXPIRES_SOON", end_date=AS_OF))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["days_until_expiration"] == 0
    assert result["risk"]["is_date_expiring_today"] is True


def test_alert_present_for_risky_student():
    svc, _, _ = _make_service(_study_right(status="EXPIRED", end_date=date(2024, 1, 1)))
    result = svc.detect_study_right_risk(1, AS_OF)
    alert = result["risk"]["alert"]
    assert alert is not None
    assert alert["student_id"] == 1
    assert alert["alert_code"] == ALERT_CODE_EXPIRED
    assert alert["risk_status"] == RISK_STATUS_EXPIRED


def test_alert_contains_required_fields():
    svc, _, _ = _make_service(_study_right(status="EXPIRES_SOON", end_date=date(2026, 3, 1)))
    result = svc.detect_study_right_risk(1, AS_OF)
    alert = result["risk"]["alert"]
    for field in ["student_id", "student_name", "study_right_id", "alert_code",
                  "alert_message", "risk_status", "expiration_date",
                  "days_until_expiration", "as_of_date"]:
        assert field in alert, f"Missing alert field: {field}"


def test_alert_none_for_safe_student():
    svc, _, _ = _make_service(_study_right(status="ACTIVE", end_date=date(2028, 5, 31)))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["alert"] is None


def test_as_of_date_in_result():
    svc, _, _ = _make_service()
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["as_of_date"] == AS_OF.isoformat()


def test_no_study_right_returns_unknown():
    svc, _, _ = _make_service(
        study_right_result={
            "success": False,
            "error": "STUDY_RIGHT_NOT_FOUND",
            "message": "Not found.",
        }
    )
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["success"] is True
    assert result["risk"]["risk_status"] == RISK_STATUS_UNKNOWN
    assert result["risk"]["requires_attention"] is False
    assert result["risk"]["alert"] is None


def test_result_contains_all_required_fields():
    svc, _, _ = _make_service()
    result = svc.detect_study_right_risk(1, AS_OF)
    risk = result["risk"]
    for field in [
        "student_id", "student_name", "programme", "as_of_date",
        "study_right_id", "status", "expiration_date", "days_until_expiration",
        "is_date_expired", "is_date_expiring_today", "risk_status",
        "requires_attention", "alert_code", "alert_message",
        "extension_count", "alert",
    ]:
        assert field in risk, f"Missing field: {field}"


def test_student_service_called_with_correct_id():
    svc, _, student_svc = _make_service()
    svc.detect_study_right_risk(42, AS_OF)
    student_svc.get_student.assert_called_once_with(42)


def test_study_right_service_called_with_correct_id():
    svc, sr_svc, _ = _make_service()
    svc.detect_study_right_risk(42, AS_OF)
    sr_svc.get_study_right.assert_called_once_with(42)


def test_result_does_not_contain_risk_score():
    """#94 must not implement #95 Risk Scoring."""
    svc, _, _ = _make_service()
    result = svc.detect_study_right_risk(1, AS_OF)
    risk = result["risk"]
    for field in ["risk_score", "academic_health_score", "recommendation",
                  "completed_ects", "expected_ects", "delay_ects"]:
        assert field not in risk, f"Field '{field}' belongs to another issue"


def test_detection_is_deterministic():
    svc1, _, _ = _make_service(_study_right(status="EXPIRES_SOON", end_date=date(2026, 3, 1)))
    svc2, _, _ = _make_service(_study_right(status="EXPIRES_SOON", end_date=date(2026, 3, 1)))
    r1 = svc1.detect_study_right_risk(1, AS_OF)
    r2 = svc2.detect_study_right_risk(1, AS_OF)
    assert r1["risk"]["risk_status"] == r2["risk"]["risk_status"]
    assert r1["risk"]["days_until_expiration"] == r2["risk"]["days_until_expiration"]


def test_two_students_not_mixed():
    svc1, _, _ = _make_service(
        _study_right(sr_id=1, status="EXPIRED", end_date=date(2024, 1, 1)),
        _student(student_id=1, name="Aino Mäkinen"),
    )
    svc2, _, _ = _make_service(
        _study_right(sr_id=2, status="ACTIVE", end_date=date(2028, 5, 31)),
        _student(student_id=2, name="Mikael Virtanen"),
    )
    r1 = svc1.detect_study_right_risk(1, AS_OF)
    r2 = svc2.detect_study_right_risk(2, AS_OF)
    assert r1["risk"]["risk_status"] == RISK_STATUS_EXPIRED
    assert r2["risk"]["risk_status"] == RISK_STATUS_SAFE
    assert r1["risk"]["student_name"] == "Aino Mäkinen"
    assert r2["risk"]["student_name"] == "Mikael Virtanen"


def test_expiration_date_in_result():
    end = date(2026, 3, 1)
    svc, _, _ = _make_service(_study_right(status="EXPIRES_SOON", end_date=end))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["expiration_date"] == end.isoformat()


def test_extension_count_in_result():
    svc, _, _ = _make_service(_study_right(status="EXTENDED", extension_count=2))
    result = svc.detect_study_right_risk(1, AS_OF)
    assert result["risk"]["extension_count"] == 2
