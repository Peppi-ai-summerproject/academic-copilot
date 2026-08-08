import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.workflows.automatic_risk_detection import (
    AutomaticRiskDetectionWorkflow,
)


class FakeActiveStudentDirectory:
    def __init__(self, student_ids=None, error=None):
        self.student_ids = student_ids if student_ids is not None else []
        self.error = error
        self.calls = []

    def list_active_student_ids(self, student_ids=None):
        self.calls.append(student_ids)
        if self.error:
            raise self.error
        return self.student_ids


class FakeRiskProvider:
    def __init__(self, assessments=None, errors=None):
        self.assessments = assessments or {}
        self.errors = errors or {}
        self.calls = []

    def assess_student_risk(
        self,
        student_id,
        *,
        as_of_date,
        allow_partial_risk_level=False,
    ):
        self.calls.append((student_id, as_of_date, allow_partial_risk_level))
        if student_id in self.errors:
            raise self.errors[student_id]
        return self.assessments[student_id]


def indicator(code, points=0):
    maximum = {
        "academic_delay": 50,
        "study_right": 30,
        "tutor_meetings": 10,
        "academic_events": 10,
    }[code]
    return {
        "indicator_code": code,
        "authoritative_source": "Canonical test risk provider",
        "normalized_input": {"source": "test"},
        "matched_rule_code": f"TEST_{code.upper()}",
        "assigned_points": points,
        "maximum_points": maximum,
        "explanation": f"{code} contributes {points} points.",
    }


def assessment(
    student_id,
    *,
    level="LOW",
    score=0,
    status="PARTIAL",
    unavailable=None,
):
    return {
        "success": True,
        "student_id": student_id,
        "assessment_status": status,
        "score": score,
        "risk_level": level,
        "score_basis": (
            "available_indicator_weights"
            if status == "PARTIAL"
            else "all_indicators"
        ),
        "policy_version": "academic-risk-v1",
        "indicator_contributions": [
            indicator("academic_delay"),
            indicator("study_right"),
        ],
        "applied_overrides": [],
        "explanation": ["Canonical test assessment."],
        "unavailable_indicators": (
            ["tutor_meetings"] if unavailable is None and status == "PARTIAL" else unavailable or []
        ),
    }


def workflow(*, student_ids=None, assessments=None, directory_error=None, risk_errors=None):
    directory = FakeActiveStudentDirectory(student_ids, directory_error)
    provider = FakeRiskProvider(assessments, risk_errors)
    return (
        AutomaticRiskDetectionWorkflow(
            active_student_directory=directory,
            risk_provider=provider,
            timezone="Europe/Helsinki",
        ),
        directory,
        provider,
    )


def test_direct_run_evaluates_only_active_ids_and_returns_deterministic_attention_order(caplog):
    instance, directory, provider = workflow(
        student_ids=[3, 1, 2],
        assessments={
            1: assessment(1, level="LOW", score=0),
            2: assessment(2, level="MEDIUM", score=22),
            3: assessment(3, level="CRITICAL", score=80, status="COMPLETE"),
        },
    )

    with caplog.at_level(
        logging.INFO,
        logger="academic-copilot.workflows.automatic_risk_detection",
    ):
        result = instance.run(
            evaluation_time=datetime(2026, 8, 5, 8, tzinfo=ZoneInfo("UTC"))
        )

    assert directory.calls == [None]
    assert provider.calls == [
        (1, datetime(2026, 8, 5).date(), True),
        (2, datetime(2026, 8, 5).date(), True),
        (3, datetime(2026, 8, 5).date(), True),
    ]
    assert result.execution_key == "risk-detection:2026-08-05"
    assert result.status == "partial"
    assert result.active_student_count == 3
    assert result.evaluated_student_count == 3
    assert result.at_risk_student_count == 2
    assert result.risk_level_counts == {
        "LOW": 1,
        "MEDIUM": 1,
        "HIGH": 0,
        "CRITICAL": 1,
    }
    assert [(item.student_id, item.risk_level) for item in result.results] == [
        (3, "CRITICAL"),
        (2, "MEDIUM"),
    ]
    assert result.unavailable_indicator_counts == {"tutor_meetings": 2}
    assert "student_id" not in caplog.text


def test_explicit_ids_are_delegated_to_the_active_student_filter():
    instance, directory, provider = workflow(
        student_ids=[2],
        assessments={2: assessment(2, level="HIGH", score=55)},
    )

    result = instance.run(
        evaluation_time=datetime(2026, 8, 5, 9, tzinfo=ZoneInfo("Europe/Helsinki")),
        student_ids=[4, 2],
    )

    assert directory.calls == [[4, 2]]
    assert provider.calls == [(2, datetime(2026, 8, 5).date(), True)]
    assert [item.student_id for item in result.results] == [2]


def test_at_risk_result_exposes_only_nonzero_indicators_as_actionable():
    instance, _, _ = workflow(
        student_ids=[2],
        assessments={
            2: {
                **assessment(2, level="HIGH", score=55),
                "indicator_contributions": [
                    indicator("academic_delay", 30),
                    indicator("study_right"),
                ],
            }
        },
    )

    result = instance.run(
        evaluation_time=datetime(2026, 8, 5, 9, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    assert result.results[0].contributing_indicators == ["academic_delay", "study_right"]
    assert result.results[0].actionable_indicators == ["academic_delay"]


def test_at_risk_result_exposes_the_existing_canonical_explanation():
    instance, _, _ = workflow(
        student_ids=[2],
        assessments={
            2: {
                **assessment(2, level="HIGH", score=55),
                "indicator_contributions": [
                    indicator("academic_delay", 30),
                    indicator("study_right", 20),
                ],
            }
        },
    )

    result = instance.run(
        evaluation_time=datetime(2026, 8, 5, 9, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    explanation = result.results[0].risk_explanation
    assert explanation["risk_score"] == result.results[0].risk_score
    assert explanation["risk_level"] == result.results[0].risk_level
    assert [factor["indicator_code"] for factor in explanation["factors"]] == [
        "academic_delay",
        "study_right",
    ]
    assert explanation["unavailable_indicators"] == ["tutor_meetings"]
    assert explanation["assessment_status"] == "PARTIAL"


def test_successful_empty_active_population_is_completed_not_unavailable():
    instance, _, provider = workflow(student_ids=[], assessments={})

    result = instance.run(
        evaluation_time=datetime(2026, 8, 5, 9, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    assert result.status == "completed"
    assert result.evaluated_student_count == 0
    assert result.at_risk_student_count == 0
    assert result.results == []
    assert provider.calls == []


def test_unavailable_canonical_assessment_is_not_reported_as_low_risk():
    instance, _, _ = workflow(
        student_ids=[1],
        assessments={1: {"success": False, "error": "STUDY_RIGHT_UNAVAILABLE"}},
    )

    result = instance.run(
        evaluation_time=datetime(2026, 8, 5, 9, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    assert result.status == "failed"
    assert result.evaluated_student_count == 0
    assert result.risk_level_counts == {
        "LOW": 0,
        "MEDIUM": 0,
        "HIGH": 0,
        "CRITICAL": 0,
    }
    assert result.errors == ["STUDY_RIGHT_UNAVAILABLE"]


def test_one_failed_student_produces_partial_batch_result():
    instance, _, _ = workflow(
        student_ids=[1, 2],
        assessments={1: assessment(1, level="HIGH", score=56)},
        risk_errors={2: RuntimeError("source unavailable")},
    )

    result = instance.run(
        evaluation_time=datetime(2026, 8, 5, 9, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    assert result.status == "partial"
    assert result.evaluated_student_count == 1
    assert result.at_risk_student_count == 1
    assert result.errors == ["RISK_ASSESSMENT_FAILED"]


def test_result_is_serializable_and_contains_no_student_name():
    instance, _, _ = workflow(
        student_ids=[1],
        assessments={1: assessment(1, level="MEDIUM", score=22)},
    )

    payload = instance.run(
        evaluation_time=datetime(2026, 8, 5, 9, tzinfo=ZoneInfo("Europe/Helsinki"))
    ).to_dict()

    assert payload["results"][0]["student_id"] == 1
    assert "student_name" not in str(payload)
