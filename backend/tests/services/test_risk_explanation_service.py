"""Issue #113 tests for deterministic explanations of Issue #95 results."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.academic_risk_scoring_service import calculate_academic_risk
from app.services.risk_explanation_service import (
    RiskExplanationInput,
    RiskExplanationService,
)


AS_OF = date(2026, 8, 5)
_DEFAULT_TUTOR = object()


def delay(ects=0):
    return {
        "success": True,
        "delay": {
            "student_id": 1,
            "is_delayed": ects > 0,
            "delay_ects": ects,
        },
    }


def study(status="SAFE"):
    return {
        "success": True,
        "risk": {
            "student_id": 1,
            "risk_status": status,
            "requires_attention": status in {"EXTENDED", "EXPIRING_SOON", "EXPIRED"},
        },
    }


def events(*items):
    return {"success": True, "events": list(items)}


def event(days):
    return {
        "id": 1,
        "event_type": "DEADLINE",
        "event_date": (AS_OF + timedelta(days=days)).isoformat(),
        "affects_all_students": True,
    }


def tutor(points=0):
    rules = {
        0: ("RECENT_TUTOR_MEETING_COMPLETED", "COMPLETED"),
        5: ("TUTOR_MEETING_UPCOMING_WITHOUT_RECENT_COMPLETION", "SCHEDULED"),
        10: ("TUTOR_MEETING_MISSED", "MISSED"),
    }
    rule, status = rules[points]
    return {
        "success": True,
        "evaluation_status": "EVALUATED",
        "assigned_points": points,
        "matched_rule_code": rule,
        "normalized_input": {
            "meeting_id": 1,
            "meeting_status": status,
            "scheduled_at": "2026-08-05T09:00:00+00:00",
            "lookback_start": "2026-05-07",
            "upcoming_end": "2026-09-04",
        },
    }


def canonical_result(
    *,
    delay_ects=0,
    study_status="SAFE",
    event_result=None,
    tutor_result=_DEFAULT_TUTOR,
    allow_partial_risk_level=False,
):
    return calculate_academic_risk(
        student_id=1,
        as_of_date=AS_OF,
        delay_result=delay(delay_ects),
        study_right_result=study(study_status),
        academic_events_result=events() if event_result is None else event_result,
        tutor_meeting_evaluation=(
            tutor(0) if tutor_result is _DEFAULT_TUTOR else tutor_result
        ),
        allow_partial_risk_level=allow_partial_risk_level,
    )


def explain(result):
    return RiskExplanationService().explain(
        RiskExplanationInput(student_id=1, risk_result=result)
    )


def test_low_risk_uses_the_existing_score_and_does_not_invent_contributors():
    result = canonical_result()

    explanation = explain(result)

    assert (explanation.risk_score, explanation.risk_level) == (0, "LOW")
    assert all(factor.contribution == 0 for factor in explanation.factors)
    assert "No verified indicator contributed risk points." in explanation.summary
    assert "Risk-increasing indicators" not in explanation.summary
    assert explanation.factors[0].evidence == {
        "is_delayed": False,
        "delay_ects": 0,
    }


def test_delay_factor_copies_existing_points_rule_and_evidence():
    result = canonical_result(delay_ects=60)

    explanation = explain(result)
    delay_factor = explanation.factors[0]

    assert explanation.risk_level == result["risk_level"] == "HIGH"
    assert delay_factor.indicator_code == "academic_delay"
    assert delay_factor.contribution == 50
    assert delay_factor.maximum_contribution == 50
    assert delay_factor.matched_rule_code == "DELAY_60_OR_MORE"
    assert delay_factor.evidence == {"is_delayed": True, "delay_ects": 60}


def test_study_right_override_is_explained_without_changing_critical_result():
    result = canonical_result(study_status="EXPIRED")

    explanation = explain(result)

    assert (explanation.risk_score, explanation.risk_level) == (70, "CRITICAL")
    assert explanation.applied_overrides == tuple(result["applied_overrides"])
    assert "STUDY_RIGHT_EXPIRED" in explanation.summary
    assert next(
        factor for factor in explanation.factors if factor.indicator_code == "study_right"
    ).contribution == 30


def test_multiple_contributors_are_ranked_by_existing_numeric_contributions():
    result = canonical_result(
        delay_ects=30,
        study_status="EXPIRING_SOON",
        event_result=events(event(5)),
        tutor_result=tutor(5),
    )

    explanation = explain(result)

    assert (explanation.risk_score, explanation.risk_level) == (65, "HIGH")
    assert [factor.indicator_code for factor in explanation.factors] == [
        "academic_delay",
        "study_right",
        "academic_events",
        "tutor_meetings",
    ]
    assert [factor.contribution for factor in explanation.factors] == [30, 20, 10, 5]


def test_partial_assessment_discloses_missing_evidence_without_treating_it_as_zero():
    result = canonical_result(
        delay_ects=30,
        study_status="EXPIRING_SOON",
        event_result=events(event(5)),
        tutor_result=None,
        allow_partial_risk_level=True,
    )

    explanation = explain(result)

    assert result["assessment_status"] == explanation.assessment_status == "PARTIAL"
    assert (explanation.risk_score, explanation.risk_level) == (
        result["score"],
        result["risk_level"],
    )
    assert explanation.unavailable_indicators == ("tutor_meetings",)
    assert "was unavailable and was not treated as zero" in explanation.summary
    assert "normalized against available indicator weights" in explanation.summary


def test_partial_assessment_without_existing_final_level_does_not_create_one():
    result = canonical_result(delay_ects=30, tutor_result=None)

    explanation = explain(result)

    assert (result["score"], result["risk_level"]) == (None, None)
    assert (explanation.risk_score, explanation.risk_level) == (None, None)
    assert "does not provide a final risk score or risk level" in explanation.summary


def test_explanations_are_deterministic_and_do_not_recalculate_the_result():
    result = canonical_result(delay_ects=30, study_status="EXPIRING_SOON")

    first = explain(result).to_dict()
    second = explain(result).to_dict()

    assert first == second
    assert first["risk_score"] == result["score"]
    assert first["risk_level"] == result["risk_level"]
    assert first["assessment_status"] == result["assessment_status"]


def test_unavailable_canonical_result_is_disclosed_without_rebuilding_risk():
    explanation = explain({"success": False, "error": "STUDY_RIGHT_UNAVAILABLE"})

    assert explanation.success is False
    assert explanation.assessment_status == "UNPROCESSABLE"
    assert explanation.risk_score is explanation.risk_level is None
    assert explanation.warnings == ("STUDY_RIGHT_UNAVAILABLE",)
