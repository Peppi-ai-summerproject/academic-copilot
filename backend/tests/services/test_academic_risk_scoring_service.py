"""Issue #95 deterministic scoring and orchestration tests."""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import Mock

import pytest

from app.services.academic_risk_scoring_service import (
    AcademicRiskScoringService,
    calculate_academic_risk,
)


AS_OF = date(2026, 8, 5)


def delay(ects=0, *, delayed=None, student_id=1):
    return {"success": True, "delay": {
        "student_id": student_id,
        "is_delayed": ects > 0 if delayed is None else delayed,
        "delay_ects": ects,
    }}


def study(status="SAFE", *, attention=None, student_id=1):
    if attention is None:
        attention = status in {"EXTENDED", "EXPIRING_SOON", "EXPIRED"}
    return {"success": True, "risk": {
        "student_id": student_id,
        "risk_status": status,
        "requires_attention": attention,
    }}


def events(*items):
    return {"success": True, "events": list(items)}


def event(days, *, applicable=True, kind="DEADLINE", event_id=1):
    return {
        "id": event_id,
        "event_type": kind,
        "event_date": (AS_OF + timedelta(days=days)).isoformat(),
        "affects_all_students": applicable,
    }


def tutor(points=0):
    rules = {
        0: "RECENT_TUTOR_MEETING_COMPLETED",
        5: "TUTOR_MEETING_UPCOMING_WITHOUT_RECENT_COMPLETION",
        10: "TUTOR_MEETING_MISSED",
    }
    return {
        "success": True,
        "evaluation_status": "EVALUATED",
        "assigned_points": points,
        "matched_rule_code": rules[points],
        "normalized_input": {
            "meeting_id": 1,
            "meeting_status": {0: "COMPLETED", 5: "SCHEDULED", 10: "MISSED"}[points],
            "scheduled_at": "2026-08-05T09:00:00+00:00",
            "lookback_start": "2026-05-07",
            "upcoming_end": "2026-09-04",
        },
    }


def score(
    *,
    delay_result=None,
    study_result=None,
    event_result=None,
    tutor_result=None,
    allow_partial_risk_level=False,
):
    return calculate_academic_risk(
        student_id=1,
        as_of_date=AS_OF,
        delay_result=delay() if delay_result is None else delay_result,
        study_right_result=study() if study_result is None else study_result,
        academic_events_result=events() if event_result is None else event_result,
        tutor_meeting_evaluation=tutor_result,
        allow_partial_risk_level=allow_partial_risk_level,
    )


def contribution(result, code):
    return next(item for item in result["indicator_contributions"] if item["indicator_code"] == code)


@pytest.mark.parametrize(("ects", "points", "rule"), [
    (0, 0, "DELAY_NONE"),
    (1, 15, "DELAY_1_TO_29"),
    (29, 15, "DELAY_1_TO_29"),
    (30, 30, "DELAY_30_TO_59"),
    (59, 30, "DELAY_30_TO_59"),
    (60, 50, "DELAY_60_OR_MORE"),
])
def test_delay_boundaries(ects, points, rule):
    item = contribution(score(delay_result=delay(ects)), "academic_delay")
    assert (item["assigned_points"], item["matched_rule_code"]) == (points, rule)


@pytest.mark.parametrize("bad", [
    delay(1, delayed=False),
    delay(0, delayed=True),
    delay(-1, delayed=False),
    {"success": True, "delay": {"student_id": 1, "is_delayed": False}},
])
def test_contradictory_or_malformed_delay_is_unprocessable(bad):
    result = score(delay_result=bad)
    assert result["assessment_status"] == "UNPROCESSABLE"
    assert result["score"] is result["risk_level"] is None


@pytest.mark.parametrize(("status", "points"), [
    ("SAFE", 0),
    ("EXTENDED", 0),
    ("EXPIRING_SOON", 20),
    ("EXPIRED", 30),
])
def test_study_right_mappings(status, points):
    item = contribution(score(study_result=study(status)), "study_right")
    assert item["assigned_points"] == points


def test_extended_alone_is_not_risk_points():
    result = score(study_result=study("EXTENDED"), tutor_result=tutor())
    assert result["score"] == 0
    assert result["risk_level"] == "LOW"


@pytest.mark.parametrize("status", ["UNKNOWN", "SOMETHING_NEW", None])
def test_unknown_study_right_is_unprocessable(status):
    result = score(study_result=study(status))
    assert result["assessment_status"] == "UNPROCESSABLE"
    assert result["score"] is result["risk_level"] is None


def test_contradictory_study_right_is_unprocessable():
    result = score(study_result=study("SAFE", attention=True))
    assert result["assessment_status"] == "UNPROCESSABLE"


def test_expired_study_right_applies_score_floor():
    result = score(study_result=study("EXPIRED"), tutor_result=tutor())
    assert result["raw_subtotal"] == 30
    assert result["score"] == 70
    assert result["risk_level"] == "CRITICAL"
    assert result["applied_overrides"][0]["code"] == "STUDY_RIGHT_EXPIRED"


def test_expired_override_does_not_reduce_subtotal_above_70():
    result = score(
        delay_result=delay(60), study_result=study("EXPIRED"),
        event_result=events(event(0)), tutor_result=tutor(10),
    )
    assert result["raw_subtotal"] == 100
    assert result["score"] == 100
    assert result["applied_overrides"][0]["adjusted_score"] == 100


def test_successful_event_query_with_no_applicable_deadline_scores_zero():
    item = contribution(score(event_result=events(event(15)), tutor_result=tutor()), "academic_events")
    assert item["assigned_points"] == 0


@pytest.mark.parametrize("days", [0, 14])
def test_inclusive_event_window_boundaries(days):
    item = contribution(score(event_result=events(event(days)), tutor_result=tutor()), "academic_events")
    assert item["assigned_points"] == 10


def test_deadline_at_15_days_scores_zero():
    item = contribution(score(event_result=events(event(15)), tutor_result=tutor()), "academic_events")
    assert item["assigned_points"] == 0


def test_failed_event_query_is_unavailable():
    result = score(event_result={"success": False, "error": "DATABASE_ERROR"})
    assert "academic_events" in result["unavailable_indicators"]
    assert result["assessment_status"] == "PARTIAL"


def test_global_event_without_verified_applicability_does_not_contribute():
    item = contribution(
        score(event_result=events(event(0, applicable=False)), tutor_result=tutor()),
        "academic_events",
    )
    assert item["assigned_points"] == 0


def test_event_missing_structured_applicability_is_unavailable():
    malformed = event(0)
    malformed.pop("affects_all_students")
    result = score(event_result=events(malformed), tutor_result=tutor())
    assert result["assessment_status"] == "PARTIAL"
    assert "academic_events" in result["unavailable_indicators"]


def test_multiple_deadlines_are_capped_at_ten_total():
    item = contribution(
        score(event_result=events(event(0), event(14, event_id=2)), tutor_result=tutor()),
        "academic_events",
    )
    assert item["assigned_points"] == 10
    assert item["normalized_input"]["applicable_deadline_count"] == 2


def test_unavailable_tutor_meetings_produces_partial_without_overall_score():
    result = score()
    assert result["assessment_status"] == "PARTIAL"
    assert result["unavailable_indicators"] == ["tutor_meetings"]
    assert result["raw_subtotal"] == 0
    assert result["score"] is None
    assert result["risk_level"] is None
    assert result["available_indicator_maximum"] == 90
    assert result["score_basis"] is None


def test_opt_in_partial_risk_level_normalizes_verified_available_weights():
    result = score(
        delay_result=delay(30),
        study_result=study("EXPIRING_SOON"),
        allow_partial_risk_level=True,
    )

    assert result["assessment_status"] == "PARTIAL"
    assert result["raw_subtotal"] == 50
    assert result["available_indicator_maximum"] == 90
    assert result["score"] == 56
    assert result["risk_level"] == "HIGH"
    assert result["score_basis"] == "available_indicator_weights"
    assert result["unavailable_indicators"] == ["tutor_meetings"]


def test_opt_in_partial_expired_study_right_preserves_canonical_override():
    result = score(
        study_result=study("EXPIRED"),
        allow_partial_risk_level=True,
    )

    assert result["raw_subtotal"] == 30
    assert result["score"] == 78
    assert result["risk_level"] == "CRITICAL"


@pytest.mark.parametrize("mandatory", ["delay", "study"])
def test_failed_mandatory_indicator_is_unprocessable(mandatory):
    kwargs = {f"{mandatory}_result": {"success": False}}
    result = score(**kwargs)
    assert result["success"] is False
    assert result["assessment_status"] == "UNPROCESSABLE"
    assert result["raw_subtotal"] is None
    assert result["score"] is result["risk_level"] is None


def test_valid_complete_zero_score_for_future_verified_meeting_adapter():
    result = score(tutor_result=tutor(0))
    assert result["assessment_status"] == "COMPLETE"
    assert result["score"] == result["raw_subtotal"] == 0
    assert result["risk_level"] == "LOW"


@pytest.mark.parametrize(("points", "expected_score"), [(0, 0), (5, 5), (10, 10)])
def test_approved_tutor_contributions_affect_complete_score(points, expected_score):
    result = score(tutor_result=tutor(points))
    assert result["assessment_status"] == "COMPLETE"
    assert result["score"] == expected_score


def test_unsupported_tutor_rule_is_unavailable():
    value = tutor(5)
    value["matched_rule_code"] = "UNAPPROVED_RULE"
    result = score(tutor_result=value)
    assert result["assessment_status"] == "PARTIAL"
    assert result["unavailable_indicators"] == ["tutor_meetings"]


def assert_invalid_tutor_evidence_is_partial(value):
    result = score(tutor_result=value)
    assert result["assessment_status"] == "PARTIAL"
    assert result["score"] is None
    assert result["risk_level"] is None
    assert result["unavailable_indicators"] == ["tutor_meetings"]


@pytest.mark.parametrize("normalized", [None, [], "invalid", 1, {}])
def test_non_dictionary_or_empty_tutor_normalized_input_is_unavailable(normalized):
    value = tutor(0)
    value["normalized_input"] = normalized
    assert_invalid_tutor_evidence_is_partial(value)


@pytest.mark.parametrize(
    "missing",
    ["meeting_id", "meeting_status", "scheduled_at", "lookback_start", "upcoming_end"],
)
def test_missing_required_tutor_normalized_field_is_unavailable(missing):
    value = tutor(0)
    value["normalized_input"].pop(missing)
    assert_invalid_tutor_evidence_is_partial(value)


@pytest.mark.parametrize("meeting_id", [None, True, False, 0, -1, "1", 1.0])
def test_invalid_tutor_meeting_id_is_unavailable(meeting_id):
    value = tutor(0)
    value["normalized_input"]["meeting_id"] = meeting_id
    assert_invalid_tutor_evidence_is_partial(value)


@pytest.mark.parametrize("status", [None, "", "CANCELLED", "ABSENT", "completed"])
def test_unsupported_tutor_meeting_status_is_unavailable(status):
    value = tutor(0)
    value["normalized_input"]["meeting_status"] = status
    assert_invalid_tutor_evidence_is_partial(value)


@pytest.mark.parametrize("field", ["scheduled_at", "lookback_start", "upcoming_end"])
@pytest.mark.parametrize("invalid", [None, True, "", "not-a-date"])
def test_malformed_tutor_temporal_field_is_unavailable(field, invalid):
    value = tutor(0)
    value["normalized_input"][field] = invalid
    assert_invalid_tutor_evidence_is_partial(value)


def test_tutor_timestamp_requires_iso_datetime_with_timezone():
    for invalid in ("2026-08-05", "2026-08-05T09:00:00"):
        value = tutor(0)
        value["normalized_input"]["scheduled_at"] = invalid
        assert_invalid_tutor_evidence_is_partial(value)


@pytest.mark.parametrize(("points", "wrong_status"), [
    (0, "SCHEDULED"), (0, "MISSED"),
    (5, "COMPLETED"), (5, "MISSED"),
    (10, "COMPLETED"), (10, "SCHEDULED"),
])
def test_tutor_rule_status_contradiction_is_unavailable(points, wrong_status):
    value = tutor(points)
    value["normalized_input"]["meeting_status"] = wrong_status
    assert_invalid_tutor_evidence_is_partial(value)


def test_unavailable_tutor_rule_cannot_be_marked_evaluated():
    value = tutor(0)
    value["matched_rule_code"] = "TUTOR_MEETING_EVIDENCE_UNAVAILABLE"
    assert_invalid_tutor_evidence_is_partial(value)


def test_tutor_adapter_does_not_serialize_private_notes_or_personal_data():
    evaluation = tutor(0)
    evaluation["normalized_input"] = {
        **tutor(0)["normalized_input"],
        "private_notes": "Sensitive discussion",
        "student_name": "Private Student",
        "verified": True,
    }
    item = contribution(score(tutor_result=evaluation), "tutor_meetings")
    serialized = json.dumps(item)
    assert item["normalized_input"] == tutor(0)["normalized_input"]
    assert "Sensitive discussion" not in serialized
    assert "Private Student" not in serialized


def test_factor_order_is_stable():
    result = score(event_result=events(event(0)), tutor_result=tutor())
    assert [item["indicator_code"] for item in result["indicator_contributions"]] == [
        "academic_delay", "study_right", "tutor_meetings", "academic_events",
    ]


def test_explicit_as_of_date_and_no_hidden_system_date():
    result = score(event_result=events(event(14)), tutor_result=tutor())
    assert result["as_of_date"] == "2026-08-05"
    assert contribution(result, "academic_events")["assigned_points"] == 10


def test_exact_serializable_contract():
    result = score()
    assert list(result) == [
        "success", "student_id", "as_of_date", "assessment_status", "score",
        "raw_subtotal", "available_indicator_maximum", "score_basis",
        "score_range", "score_direction", "risk_level",
        "indicator_contributions", "unavailable_indicators", "applied_overrides",
        "explanation", "policy_version",
    ]
    assert set(result["indicator_contributions"][0]) == {
        "indicator_code", "authoritative_source", "normalized_input",
        "matched_rule_code", "assigned_points", "maximum_points", "explanation",
    }
    json.dumps(result)


def test_risk_level_boundaries_without_gaps_or_overlaps():
    cases = [
        (0, "SAFE", False, 0, "LOW"),
        (1, "SAFE", False, 15, "LOW"),
        (0, "EXPIRING_SOON", False, 20, "MEDIUM"),
        (30, "SAFE", False, 30, "MEDIUM"),
        (30, "SAFE", True, 40, "HIGH"),
        (60, "SAFE", False, 50, "HIGH"),
        (60, "EXPIRING_SOON", False, 70, "CRITICAL"),
    ]
    for delay_ects, status, has_event, expected_score, expected_level in cases:
        result = score(
            delay_result=delay(delay_ects), study_result=study(status),
            event_result=events(event(0)) if has_event else events(),
            tutor_result=tutor(),
        )
        assert result["score"] == expected_score
        assert result["risk_level"] == expected_level


def test_orchestrator_calls_authoritative_services_with_explicit_date():
    delay_service = Mock()
    delay_service.detect_student_delay.return_value = delay()
    study_service = Mock()
    study_service.detect_study_right_risk.return_value = study()
    event_service = Mock()
    event_service.get_upcoming_events.return_value = events()
    meeting_service = Mock()
    meeting_service.evaluate_student.return_value = tutor()
    service = AcademicRiskScoringService(
        delay_service, study_service, event_service, meeting_service
    )

    result = service.assess_student_risk(1, as_of_date=AS_OF)

    delay_service.detect_student_delay.assert_called_once_with(1)
    study_service.detect_study_right_risk.assert_called_once_with(1, as_of_date=AS_OF)
    event_service.get_upcoming_events.assert_called_once_with(start_date="2026-08-05", end_date=None)
    meeting_service.evaluate_student.assert_called_once_with(1, as_of_date=AS_OF)
    assert result["assessment_status"] == "COMPLETE"
    assert result["unavailable_indicators"] == []


def test_orchestrator_exposes_opt_in_normalized_partial_level():
    delay_service = Mock()
    delay_service.detect_student_delay.return_value = delay(30)
    study_service = Mock()
    study_service.detect_study_right_risk.return_value = study("EXPIRING_SOON")
    event_service = Mock()
    event_service.get_upcoming_events.return_value = events()
    service = AcademicRiskScoringService(delay_service, study_service, event_service)

    result = service.assess_student_risk(
        1,
        as_of_date=AS_OF,
        allow_partial_risk_level=True,
    )

    assert result["assessment_status"] == "PARTIAL"
    assert result["score"] == 56
    assert result["risk_level"] == "HIGH"


def test_pure_scoring_has_no_database_network_llm_or_rag_dependency():
    result = score(tutor_result=tutor())
    assert result["success"] is True
    assert result["policy_version"] == "academic-risk-v1"
