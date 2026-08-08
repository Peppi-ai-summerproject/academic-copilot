"""Academic Health Score contract tests for Issue #96."""

from copy import deepcopy
from datetime import date
from unittest.mock import Mock

import pytest

from app.services.academic_health_score_service import (
    AcademicHealthScoreService,
    calculate_academic_health,
    classify_health_score,
)
from app.services.academic_risk_scoring_service import classify_risk_score
from app.services.academic_risk_scoring_service import calculate_academic_risk


AS_OF = date(2026, 8, 8)
MAXIMUMS = {
    "academic_delay": 50,
    "study_right": 30,
    "tutor_meetings": 10,
    "academic_events": 10,
}


def risk_assessment(points=None, *, status="COMPLETE", unavailable=None, overrides=None):
    assigned = points or {code: 0 for code in MAXIMUMS}
    contributions = [
        {
            "indicator_code": code,
            "assigned_points": assigned.get(code, 0),
            "maximum_points": maximum,
            "matched_rule_code": (
                "STUDY_RIGHT_EXPIRED"
                if code == "study_right"
                and any(item.get("code") == "STUDY_RIGHT_EXPIRED" for item in (overrides or []))
                else f"{code.upper()}_RULE"
            ),
        }
        for code, maximum in MAXIMUMS.items()
        if code not in (unavailable or [])
    ]
    raw = sum(item["assigned_points"] for item in contributions)
    applied = overrides or []
    score = raw
    if applied:
        score = applied[-1]["adjusted_score"]
    return {
        "success": True,
        "student_id": 1,
        "assessment_status": status,
        "score": score if status == "COMPLETE" else None,
        "risk_level": classify_risk_score(score) if status == "COMPLETE" else None,
        "score_basis": "all_indicators" if status == "COMPLETE" else None,
        "raw_subtotal": raw,
        "indicator_contributions": contributions,
        "unavailable_indicators": unavailable or [],
        "applied_overrides": applied,
        "policy_version": "academic-risk-v1",
    }


@pytest.mark.parametrize(
    ("score", "level"),
    [(0, "URGENT_SUPPORT"), (30, "URGENT_SUPPORT"), (31, "NEEDS_ATTENTION"),
     (60, "NEEDS_ATTENTION"), (61, "STABLE"), (80, "STABLE"),
     (81, "STRONG"), (100, "STRONG")],
)
def test_interpretation_boundaries_are_complete(score, level):
    assert classify_health_score(score) == level


def test_clearly_healthy_student_scores_maximum():
    result = calculate_academic_health(risk_assessment())
    assert result["health_score"] == 100
    assert result["health_level"] == "STRONG"


def test_mixed_student_has_stable_health():
    result = calculate_academic_health(risk_assessment({"academic_delay": 30, "study_right": 0}))
    assert result["health_score"] == 70
    assert result["health_level"] == "STABLE"


def test_high_risk_student_has_low_health():
    result = calculate_academic_health(risk_assessment({
        "academic_delay": 50, "study_right": 30,
        "tutor_meetings": 10, "academic_events": 10,
    }))
    assert result["health_score"] == 0
    assert result["health_level"] == "URGENT_SUPPORT"


def test_components_explain_all_weights_and_inverse_relationship():
    risk = risk_assessment({"academic_delay": 15, "study_right": 20, "tutor_meetings": 5})
    result = calculate_academic_health(risk)
    assert sum(item["maximum_points"] for item in result["components"]) == 100
    assert sum(item["health_points"] for item in result["components"]) == result["health_score"]
    assert result["health_score"] + risk["score"] == 100


def test_expired_study_right_floor_is_an_explicit_adjustment():
    override = [{
        "code": "STUDY_RIGHT_EXPIRED",
        "minimum_score": 70,
        "raw_subtotal": 30,
        "adjusted_score": 70,
    }]
    result = calculate_academic_health(
        risk_assessment({"study_right": 30}, overrides=override)
    )
    assert result["health_score"] == 30
    assert result["adjustments"] == [{
        "code": "STUDY_RIGHT_EXPIRED",
        "health_point_adjustment": -40,
        "explanation": "STUDY_RIGHT_EXPIRED reduces health by 40 additional points to preserve the canonical risk override.",
    }]
    assert sum(item["health_points"] for item in result["components"]) - 40 == 30


def test_partial_evidence_never_reports_authoritative_numeric_health():
    result = calculate_academic_health(
        risk_assessment(status="PARTIAL", unavailable=["tutor_meetings"])
    )
    assert result["success"] is True
    assert result["assessment_status"] == "PARTIAL"
    assert result["health_score"] is result["health_level"] is None
    assert result["missing_indicators"] == ["tutor_meetings"]
    assert result["available_component_maximum"] == 90


def test_valid_numeric_partial_risk_deliberately_has_null_health():
    value = risk_assessment(status="PARTIAL", unavailable=["tutor_meetings"])
    value["score"] = 56
    value["risk_level"] = "HIGH"
    value["score_basis"] = "available_indicator_weights"

    result = calculate_academic_health(value)

    assert result["success"] is True
    assert result["assessment_status"] == "PARTIAL"
    assert result["health_score"] is None
    assert result["health_level"] is None
    assert result["missing_indicators"] == ["tutor_meetings"]


@pytest.mark.parametrize("envelope", ["duplicate", "missing", "extra", "override"])
def test_noncanonical_component_envelopes_are_rejected(envelope):
    value = risk_assessment()
    if envelope == "duplicate":
        value["indicator_contributions"][1]["indicator_code"] = "academic_delay"
    elif envelope == "missing":
        value["indicator_contributions"].pop()
    elif envelope == "extra":
        value["indicator_contributions"][-1]["indicator_code"] = "invented_indicator"
    else:
        value["applied_overrides"] = [
            {"code": "INVENTED_OVERRIDE", "raw_subtotal": 0, "adjusted_score": 0}
        ]

    result = calculate_academic_health(value)

    assert result["success"] is False
    assert result["assessment_status"] == "UNPROCESSABLE"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(score=101),
        lambda value: value["indicator_contributions"][0].update(assigned_points=-1),
        lambda value: value["indicator_contributions"][0].update(maximum_points=0),
        lambda value: value.update(unavailable_indicators="tutor_meetings"),
    ],
)
def test_malformed_canonical_evidence_is_rejected(mutation):
    value = risk_assessment()
    mutation(value)
    result = calculate_academic_health(value)
    assert result["success"] is False
    assert result["assessment_status"] == "UNPROCESSABLE"


def test_repeated_evaluation_is_deterministic():
    value = risk_assessment({"academic_delay": 15, "academic_events": 10})
    assert calculate_academic_health(deepcopy(value)) == calculate_academic_health(deepcopy(value))


def test_service_calls_canonical_risk_without_partial_normalization():
    risk_service = Mock()
    risk_service.assess_student_risk.return_value = risk_assessment()
    service = AcademicHealthScoreService(risk_service)
    result = service.assess_student_health(1, as_of_date=AS_OF)
    risk_service.assess_student_risk.assert_called_once_with(
        1, as_of_date=AS_OF, allow_partial_risk_level=False
    )
    assert result["health_score"] == 100


def test_service_failure_is_visible_not_treated_as_healthy():
    risk_service = Mock()
    risk_service.assess_student_risk.side_effect = RuntimeError("down")
    result = AcademicHealthScoreService(risk_service).assess_student_health(1, as_of_date=AS_OF)
    assert result["success"] is False
    assert result["health_score"] is None
    assert result["missing_indicators"] == ["RISK_ASSESSMENT_UNAVAILABLE"]


def test_contradictory_complete_score_and_level_are_rejected():
    value = risk_assessment({"academic_delay": 50, "study_right": 20})
    value["risk_level"] = "LOW"

    result = calculate_academic_health(value)

    assert result["success"] is False
    assert result["missing_indicators"] == ["RISK_ASSESSMENT_MALFORMED"]


def test_unknown_canonical_policy_version_is_rejected():
    value = risk_assessment()
    value["policy_version"] = "academic-risk-v2"

    result = calculate_academic_health(value)

    assert result["success"] is False
    assert result["assessment_status"] == "UNPROCESSABLE"


def test_partial_numeric_score_must_have_matching_canonical_level():
    value = risk_assessment(status="PARTIAL", unavailable=["tutor_meetings"])
    value.update(
        score=70,
        risk_level="LOW",
        score_basis="available_indicator_weights",
    )

    result = calculate_academic_health(value)

    assert result["success"] is False
    assert result["health_score"] is None


def test_returned_unsuccessful_canonical_result_is_not_converted_to_health():
    result = calculate_academic_health({
        "success": False,
        "error": "STUDY_RIGHT_RISK_UNAVAILABLE",
    })

    assert result["success"] is False
    assert result["assessment_status"] == "UNPROCESSABLE"
    assert result["health_score"] is None
    assert result["health_level"] is None


def test_real_issue_95_assessment_is_converted_without_recalculating_risk():
    canonical = calculate_academic_risk(
        student_id=1,
        as_of_date=AS_OF,
        delay_result={
            "success": True,
            "delay": {"student_id": 1, "is_delayed": True, "delay_ects": 30},
        },
        study_right_result={
            "success": True,
            "risk": {
                "student_id": 1,
                "risk_status": "EXPIRING_SOON",
                "requires_attention": True,
            },
        },
        academic_events_result={"success": True, "events": []},
        tutor_meeting_evaluation={
            "success": True,
            "evaluation_status": "EVALUATED",
            "assigned_points": 0,
            "matched_rule_code": "RECENT_TUTOR_MEETING_COMPLETED",
            "normalized_input": {
                "meeting_id": 1,
                "meeting_status": "COMPLETED",
                "scheduled_at": "2026-08-08T09:00:00+00:00",
                "lookback_start": "2026-05-10",
                "upcoming_end": "2026-09-07",
            },
        },
    )

    result = calculate_academic_health(canonical)

    assert (canonical["score"], canonical["risk_level"]) == (50, "HIGH")
    assert (result["health_score"], result["health_level"]) == (
        50,
        "NEEDS_ATTENTION",
    )
    assert result["health_score"] + canonical["score"] == 100
