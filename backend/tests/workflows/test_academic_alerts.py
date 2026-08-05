from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.workflows.academic_alerts import (
    ALERT_TYPE_ACADEMIC_RISK_DETECTED,
    ALERT_TYPE_DELAYED_PROGRESS,
    AcademicAlertWorkflow,
)
from app.workflows.automatic_risk_detection import (
    RiskDetectionWorkflowResult,
    StudentRiskDetectionResult,
)


class FakeActiveStudentDirectory:
    def __init__(self, student_ids: list[int]) -> None:
        self.student_ids = student_ids
        self.calls = 0

    def list_active_student_ids(self) -> list[int]:
        self.calls += 1
        return self.student_ids


class FakeDelayProvider:
    def __init__(self, results: dict[int, dict]) -> None:
        self.results = results
        self.calls: list[int] = []

    def detect_student_delay(self, student_id: int) -> dict:
        self.calls.append(student_id)
        return self.results[student_id]


class FakeStudyRightProvider:
    def __init__(self, results: dict[int, dict]) -> None:
        self.results = results
        self.calls: list[tuple[int, object]] = []

    def detect_study_right_risk(self, student_id: int, *, as_of_date=None) -> dict:
        self.calls.append((student_id, as_of_date))
        return self.results[student_id]


def delay_result(student_id: int, *, delayed: bool, delay_ects: int = 0) -> dict:
    return {
        "success": True,
        "delay": {
            "student_id": student_id,
            "is_delayed": delayed,
            "delay_ects": delay_ects,
            "completed_ects": 60,
            "expected_ects": 60 + delay_ects,
            "student_name": "Sensitive Student",
            "student_number": "S-001",
        },
    }


def study_right_result(
    student_id: int,
    *,
    alert_code: str | None = None,
    risk_status: str = "SAFE",
) -> dict:
    attention = alert_code is not None
    alert = (
        {
            "student_id": student_id,
            "student_name": "Sensitive Student",
            "student_number": "S-001",
            "alert_code": alert_code,
        }
        if attention
        else None
    )
    return {
        "success": True,
        "risk": {
            "student_id": student_id,
            "risk_status": risk_status,
            "requires_attention": attention,
            "alert_code": alert_code,
            "alert": alert,
            "expiration_date": "2026-02-01" if attention else None,
            "days_until_expiration": 10 if attention else None,
            "extension_count": 1 if alert_code == "STUDY_RIGHT_EXTENDED" else 0,
            "student_name": "Sensitive Student",
        },
    }


def risk(
    student_id: int,
    *,
    level: str = "HIGH",
    actionable: list[str] | None = None,
) -> StudentRiskDetectionResult:
    return StudentRiskDetectionResult(
        student_id=student_id,
        risk_level=level,
        risk_score=55,
        assessment_status="COMPLETE",
        requires_tutor_attention=True,
        contributing_indicators=list(actionable or []),
        unavailable_indicators=[],
        score_basis="all_indicators",
        policy_version="academic-risk-v1",
        actionable_indicators=list(actionable or []),
    )


def risk_result(
    *,
    status: str = "completed",
    results: list[StudentRiskDetectionResult] | None = None,
    errors: list[str] | None = None,
) -> RiskDetectionWorkflowResult:
    return RiskDetectionWorkflowResult(
        workflow_name="automatic_risk_detection",
        execution_key="risk-detection:2026-01-01",
        evaluated_at="2026-01-01T07:00:00+02:00",
        status=status,  # type: ignore[arg-type]
        active_student_count=3,
        evaluated_student_count=3,
        at_risk_student_count=len(results or []),
        risk_level_counts={"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0},
        results=results or [],
        errors=errors or [],
    )


def workflow(
    *,
    student_ids: list[int],
    delays: dict[int, dict],
    study_rights: dict[int, dict],
) -> tuple[AcademicAlertWorkflow, FakeDelayProvider, FakeStudyRightProvider]:
    delay_provider = FakeDelayProvider(delays)
    study_right_provider = FakeStudyRightProvider(study_rights)
    return (
        AcademicAlertWorkflow(
            active_student_directory=FakeActiveStudentDirectory(student_ids),
            delay_provider=delay_provider,
            study_right_provider=study_right_provider,
            timezone="Europe/Helsinki",
        ),
        delay_provider,
        study_right_provider,
    )


def test_direct_generation_normalizes_sources_and_suppresses_overlapping_risk_alerts():
    instance, delay_provider, study_right_provider = workflow(
        student_ids=[3, 1, 2],
        delays={
            1: delay_result(1, delayed=True, delay_ects=20),
            2: delay_result(2, delayed=False),
            3: delay_result(3, delayed=False),
        },
        study_rights={
            1: study_right_result(1),
            2: study_right_result(
                2,
                alert_code="STUDY_RIGHT_EXPIRED",
                risk_status="EXPIRED",
            ),
            3: study_right_result(3),
        },
    )

    result = instance.run(
        evaluation_time=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")),
        risk_detection_result=risk_result(
            results=[
                risk(1, actionable=["academic_delay"]),
                risk(2, level="CRITICAL", actionable=["study_right"]),
                risk(3, level="MEDIUM"),
            ]
        ),
    )

    assert result.status == "completed"
    assert [(alert.affected_student_id, alert.alert_type) for alert in result.alerts] == [
        (1, ALERT_TYPE_DELAYED_PROGRESS),
        (2, "STUDY_RIGHT_EXPIRED"),
        (3, ALERT_TYPE_ACADEMIC_RISK_DETECTED),
    ]
    assert result.alerts[0].severity is None
    assert result.alerts[2].severity == "MEDIUM"
    assert result.suppressed_overall_risk_alert_count == 2
    assert delay_provider.calls == [1, 2, 3]
    assert [call[0] for call in study_right_provider.calls] == [1, 2, 3]
    assert "Sensitive Student" not in str(result.to_dict())
    assert "S-001" not in str(result.to_dict())


def test_missing_delay_data_is_partial_and_is_not_reported_as_no_delay():
    instance, _, _ = workflow(
        student_ids=[1],
        delays={1: {"success": False, "error": "CURRICULUM_NOT_FOUND"}},
        study_rights={1: study_right_result(1)},
    )

    result = instance.run(
        evaluation_time=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")),
        risk_detection_result=risk_result(status="partial"),
    )

    assert result.status == "partial"
    assert result.alerts == []
    assert result.source_statuses["delayed_progress"] == "failed"
    assert "CURRICULUM_NOT_FOUND" in result.errors
    assert "treated as safe" in result.warnings[0]


def test_empty_active_scope_is_completed_with_no_alerts():
    instance, delay_provider, study_right_provider = workflow(
        student_ids=[],
        delays={},
        study_rights={},
    )

    result = instance.run(
        evaluation_time=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")),
        risk_detection_result=risk_result(),
    )

    assert result.status == "completed"
    assert result.students_considered == 0
    assert result.alert_count == 0
    assert delay_provider.calls == []
    assert study_right_provider.calls == []


def test_failed_or_out_of_scope_risk_results_do_not_create_alerts():
    instance, _, _ = workflow(
        student_ids=[1],
        delays={1: delay_result(1, delayed=False)},
        study_rights={1: study_right_result(1)},
    )

    failed = instance.run(
        evaluation_time=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")),
        risk_detection_result=risk_result(
            status="failed",
            results=[risk(1)],
            errors=["RISK_ASSESSMENT_FAILED"],
        ),
    )
    out_of_scope = instance.run(
        evaluation_time=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")),
        risk_detection_result=risk_result(results=[risk(99)]),
    )

    assert failed.status == "partial"
    assert failed.alerts == []
    assert failed.source_statuses["overall_risk"] == "failed"
    assert out_of_scope.status == "partial"
    assert out_of_scope.alerts == []
    assert "RISK_DETECTION_RESULT_STUDENT_SCOPE_MISMATCH" in out_of_scope.errors
