"""Deterministic academic-alert generation for Issue #106.

Issue #106 normalizes established academic facts into typed, student-linked
alerts.  It does not create a scheduler, calculate academic indicators, send
notifications, persist alerts, or resolve recipients.  The daily workflow
(Issue #102) owns automatic invocation and supplies the already-computed
Issue #104 risk result.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.db.database import SessionLocal
from app.repositories.progress_repository import ProgressRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.services.delay_detection_service import DelayDetectionService
from app.services.progress_service import ProgressService
from app.services.student_service import StudentService
from app.services.study_right_risk_service import StudyRightRiskService
from app.services.study_right_service import StudyRightService
from app.workflows.automatic_risk_detection import (
    RiskDetectionWorkflowResult,
    StudentRiskDetectionResult,
)


logger = logging.getLogger("academic-copilot.workflows.academic_alerts")

ACADEMIC_ALERT_WORKFLOW_NAME = "academic_alert_generation"
ALERT_TYPE_DELAYED_PROGRESS = "DELAYED_PROGRESS"
ALERT_TYPE_ACADEMIC_RISK_DETECTED = "ACADEMIC_RISK_DETECTED"
STUDY_RIGHT_ALERT_TYPES = frozenset(
    {
        "STUDY_RIGHT_EXPIRED",
        "STUDY_RIGHT_EXPIRING_SOON",
        "STUDY_RIGHT_EXTENDED",
    }
)

AlertGenerationStatus = Literal["completed", "partial", "failed"]
SourceStatus = Literal["completed", "partial", "failed"]
AlertSource = Literal["delayed_progress", "study_right", "overall_risk"]


class ActiveStudentDirectory(Protocol):
    def list_active_student_ids(self) -> list[int]: ...


class DelayProvider(Protocol):
    def detect_student_delay(self, student_id: int) -> dict[str, Any]: ...


class StudyRightRiskProvider(Protocol):
    def detect_study_right_risk(
        self,
        student_id: int,
        as_of_date: date | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DelayedProgressAlertSource:
    """The minimal established Issue #93 facts needed for a delay alert."""

    student_id: int
    is_delayed: bool
    delay_ects: int
    completed_ects: int
    expected_ects: int


@dataclass(frozen=True)
class StudyRightAlertSource:
    """The minimal established Issue #94 alert facts, with no student name."""

    student_id: int
    alert_code: str | None
    risk_status: str
    requires_attention: bool
    expiration_date: str | None
    days_until_expiration: int | None
    extension_count: int


@dataclass(frozen=True)
class StudentAcademicAlertSources:
    """One ACTIVE student's typed source results and their availability."""

    student_id: int
    delayed_progress: DelayedProgressAlertSource | None
    study_right: StudyRightAlertSource | None
    overall_risk: StudentRiskDetectionResult | None


@dataclass(frozen=True)
class AcademicAlertInput:
    """Dependency-free input assembled from canonical Issue #93, #94, and #104 results."""

    generated_at: datetime
    evaluation_date: date
    students: list[StudentAcademicAlertSources]
    source_statuses: dict[AlertSource, SourceStatus]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AcademicAlert:
    """A serializable, student-linked alert without presentation or recipient data."""

    alert_type: str
    affected_student_id: int
    source: AlertSource
    severity: str | None
    evidence: dict[str, Any]
    occurrence_date: str | None = None


@dataclass(frozen=True)
class AcademicAlertGenerationResult:
    """One non-persistent result that #102 and future delivery code can consume."""

    workflow_name: str
    generated_at: str
    evaluation_date: str
    status: AlertGenerationStatus
    students_considered: int
    alert_count: int
    alert_type_counts: dict[str, int]
    source_statuses: dict[AlertSource, SourceStatus]
    alerts: list[AcademicAlert] = field(default_factory=list)
    suppressed_overall_risk_alert_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AcademicAlertGenerator:
    """Pure normalization and suppression policy for already-computed sources."""

    def generate(self, alert_input: AcademicAlertInput) -> AcademicAlertGenerationResult:
        _validate_input(alert_input)
        alerts: list[AcademicAlert] = []
        suppressed_overall_risk = 0

        for student in sorted(alert_input.students, key=lambda item: item.student_id):
            covered_indicators: set[str] = set()
            delay_alert = _delay_alert(student.delayed_progress)
            if delay_alert is not None:
                alerts.append(delay_alert)
                covered_indicators.add("academic_delay")

            study_right_alert = _study_right_alert(student.study_right)
            if study_right_alert is not None:
                alerts.append(study_right_alert)
                covered_indicators.add("study_right")

            risk_alert = _overall_risk_alert(student.overall_risk, covered_indicators)
            if risk_alert is None and student.overall_risk is not None:
                actionable = set(student.overall_risk.actionable_indicators)
                if actionable.intersection(covered_indicators):
                    suppressed_overall_risk += 1
            elif risk_alert is not None:
                alerts.append(risk_alert)

        sorted_alerts = sorted(
            alerts,
            key=lambda item: (
                item.affected_student_id,
                item.alert_type,
                item.occurrence_date or "",
            ),
        )
        statuses = alert_input.source_statuses.values()
        status = _aggregate_status(statuses)
        warning_values = list(alert_input.warnings)
        if status == "partial":
            warning_values.append(
                "Some canonical alert sources were unavailable; no missing source was treated as safe."
            )

        return AcademicAlertGenerationResult(
            workflow_name=ACADEMIC_ALERT_WORKFLOW_NAME,
            generated_at=alert_input.generated_at.isoformat(),
            evaluation_date=alert_input.evaluation_date.isoformat(),
            status=status,
            students_considered=len(alert_input.students),
            alert_count=len(sorted_alerts),
            alert_type_counts=_alert_type_counts(sorted_alerts),
            source_statuses=dict(alert_input.source_statuses),
            alerts=sorted_alerts,
            suppressed_overall_risk_alert_count=suppressed_overall_risk,
            warnings=_deduplicate(warning_values),
            errors=_deduplicate(alert_input.errors),
        )


class AcademicAlertWorkflow:
    """Collect canonical sources and invoke the pure Issue #106 generator.

    It has no scheduler.  The supplied #104 result is deliberately reused so
    daily automatic invocation does not calculate overall risk a second time.
    """

    def __init__(
        self,
        *,
        active_student_directory: ActiveStudentDirectory,
        delay_provider: DelayProvider,
        study_right_provider: StudyRightRiskProvider,
        timezone: str,
        generator: AcademicAlertGenerator | None = None,
    ) -> None:
        self._active_student_directory = active_student_directory
        self._delay_provider = delay_provider
        self._study_right_provider = study_right_provider
        self._timezone = _load_timezone(timezone)
        self._generator = generator or AcademicAlertGenerator()

    def run(
        self,
        *,
        evaluation_time: datetime,
        risk_detection_result: RiskDetectionWorkflowResult,
    ) -> AcademicAlertGenerationResult:
        local_time = _as_local_datetime(evaluation_time, self._timezone)
        try:
            student_ids = _validated_student_ids(
                self._active_student_directory.list_active_student_ids()
            )
        except Exception:
            logger.exception("Academic alert generation could not list active students")
            return _failed_result(
                generated_at=local_time,
                error="ACTIVE_STUDENT_DIRECTORY_UNAVAILABLE",
            )

        risk_results, risk_status, risk_errors = _risk_results(risk_detection_result)
        unexpected_risk_ids = set(risk_results).difference(student_ids)
        if unexpected_risk_ids:
            risk_results = {}
            risk_status = "failed"
            risk_errors.append("RISK_DETECTION_RESULT_STUDENT_SCOPE_MISMATCH")
        delay_statuses: list[bool] = []
        study_right_statuses: list[bool] = []
        errors = list(risk_errors)
        students: list[StudentAcademicAlertSources] = []

        for student_id in student_ids:
            delay, delay_error = self._load_delay(student_id)
            study_right, study_right_error = self._load_study_right(
                student_id,
                local_time.date(),
            )
            delay_statuses.append(delay is not None)
            study_right_statuses.append(study_right is not None)
            if delay_error is not None:
                errors.append(delay_error)
            if study_right_error is not None:
                errors.append(study_right_error)
            students.append(
                StudentAcademicAlertSources(
                    student_id=student_id,
                    delayed_progress=delay,
                    study_right=study_right,
                    overall_risk=risk_results.get(student_id),
                )
            )

        source_statuses: dict[AlertSource, SourceStatus] = {
            "delayed_progress": _source_status(delay_statuses),
            "study_right": _source_status(study_right_statuses),
            "overall_risk": risk_status,
        }
        return self._generator.generate(
            AcademicAlertInput(
                generated_at=local_time,
                evaluation_date=local_time.date(),
                students=students,
                source_statuses=source_statuses,
                errors=errors,
            )
        )

    def _load_delay(
        self,
        student_id: int,
    ) -> tuple[DelayedProgressAlertSource | None, str | None]:
        try:
            result = self._delay_provider.detect_student_delay(student_id)
        except Exception:
            logger.exception("Academic alert delay source failed")
            return None, "DELAY_SOURCE_UNAVAILABLE"
        return _parse_delay_result(result, student_id)

    def _load_study_right(
        self,
        student_id: int,
        evaluation_date: date,
    ) -> tuple[StudyRightAlertSource | None, str | None]:
        try:
            result = self._study_right_provider.detect_study_right_risk(
                student_id,
                as_of_date=evaluation_date,
            )
        except Exception:
            logger.exception("Academic alert study-right source failed")
            return None, "STUDY_RIGHT_SOURCE_UNAVAILABLE"
        return _parse_study_right_result(result, student_id)


def create_database_academic_alert_workflow(
    *,
    session: Any,
    timezone: str,
) -> AcademicAlertWorkflow:
    """Wire Issue #106 only to existing repository and service contracts."""

    student_repository = StudentRepository(session)
    progress_service = ProgressService(ProgressRepository(session))
    delay_service = DelayDetectionService(progress_service)
    study_right_service = StudyRightService(StudyRightRepository(session))
    study_right_risk_service = StudyRightRiskService(
        study_right_service,
        StudentService(student_repository),
    )
    return AcademicAlertWorkflow(
        active_student_directory=student_repository,
        delay_provider=delay_service,
        study_right_provider=study_right_risk_service,
        timezone=timezone,
    )


def run_database_academic_alert_workflow(
    *,
    evaluation_time: datetime,
    risk_detection_result: RiskDetectionWorkflowResult,
) -> AcademicAlertGenerationResult:
    """Direct, non-scheduled database entry point for an existing risk result."""

    session = SessionLocal()
    try:
        workflow = create_database_academic_alert_workflow(
            session=session,
            timezone=settings.daily_workflow_timezone,
        )
        return workflow.run(
            evaluation_time=evaluation_time,
            risk_detection_result=risk_detection_result,
        )
    finally:
        session.close()


def _delay_alert(source: DelayedProgressAlertSource | None) -> AcademicAlert | None:
    if source is None or not source.is_delayed:
        return None
    return AcademicAlert(
        alert_type=ALERT_TYPE_DELAYED_PROGRESS,
        affected_student_id=source.student_id,
        source="delayed_progress",
        severity=None,
        evidence={
            "delay_ects": source.delay_ects,
            "completed_ects": source.completed_ects,
            "expected_ects": source.expected_ects,
        },
    )


def _study_right_alert(source: StudyRightAlertSource | None) -> AcademicAlert | None:
    if (
        source is None
        or not source.requires_attention
        or source.alert_code not in STUDY_RIGHT_ALERT_TYPES
    ):
        return None
    return AcademicAlert(
        alert_type=source.alert_code,
        affected_student_id=source.student_id,
        source="study_right",
        severity=None,
        evidence={
            "risk_status": source.risk_status,
            "expiration_date": source.expiration_date,
            "days_until_expiration": source.days_until_expiration,
            "extension_count": source.extension_count,
        },
        occurrence_date=source.expiration_date,
    )


def _overall_risk_alert(
    source: StudentRiskDetectionResult | None,
    covered_indicators: set[str],
) -> AcademicAlert | None:
    if source is None or not source.requires_tutor_attention:
        return None
    if set(source.actionable_indicators).intersection(covered_indicators):
        return None
    return AcademicAlert(
        alert_type=ALERT_TYPE_ACADEMIC_RISK_DETECTED,
        affected_student_id=source.student_id,
        source="overall_risk",
        severity=source.risk_level,
        evidence={
            "risk_score": source.risk_score,
            "assessment_status": source.assessment_status,
            "contributing_indicators": list(source.contributing_indicators),
            "actionable_indicators": list(source.actionable_indicators),
            "unavailable_indicators": list(source.unavailable_indicators),
            "score_basis": source.score_basis,
            "policy_version": source.policy_version,
        },
    )


def _parse_delay_result(
    result: Any,
    student_id: int,
) -> tuple[DelayedProgressAlertSource | None, str | None]:
    if not isinstance(result, dict) or result.get("success") is not True:
        return None, _result_code(result, "DELAY_SOURCE_UNAVAILABLE")
    delay = result.get("delay")
    if not isinstance(delay, dict) or delay.get("student_id") != student_id:
        return None, "DELAY_SOURCE_MALFORMED"
    is_delayed = delay.get("is_delayed")
    delay_ects = delay.get("delay_ects")
    completed_ects = delay.get("completed_ects")
    expected_ects = delay.get("expected_ects")
    if (
        not isinstance(is_delayed, bool)
        or not _is_nonnegative_int(delay_ects)
        or not _is_nonnegative_int(completed_ects)
        or not _is_nonnegative_int(expected_ects)
        or (is_delayed and delay_ects <= 0)
        or (not is_delayed and delay_ects != 0)
    ):
        return None, "DELAY_SOURCE_MALFORMED"
    return (
        DelayedProgressAlertSource(
            student_id=student_id,
            is_delayed=is_delayed,
            delay_ects=delay_ects,
            completed_ects=completed_ects,
            expected_ects=expected_ects,
        ),
        None,
    )


def _parse_study_right_result(
    result: Any,
    student_id: int,
) -> tuple[StudyRightAlertSource | None, str | None]:
    if not isinstance(result, dict) or result.get("success") is not True:
        return None, _result_code(result, "STUDY_RIGHT_SOURCE_UNAVAILABLE")
    risk = result.get("risk")
    if not isinstance(risk, dict) or risk.get("student_id") != student_id:
        return None, "STUDY_RIGHT_SOURCE_MALFORMED"
    risk_status = risk.get("risk_status")
    attention = risk.get("requires_attention")
    alert_code = risk.get("alert_code")
    alert = risk.get("alert")
    if not isinstance(risk_status, str) or not isinstance(attention, bool):
        return None, "STUDY_RIGHT_SOURCE_MALFORMED"
    if alert_code is not None and not isinstance(alert_code, str):
        return None, "STUDY_RIGHT_SOURCE_MALFORMED"
    if attention:
        if (
            not isinstance(alert, dict)
            or alert.get("student_id") != student_id
            or alert.get("alert_code") != alert_code
            or alert_code not in STUDY_RIGHT_ALERT_TYPES
        ):
            return None, "STUDY_RIGHT_SOURCE_MALFORMED"
    elif alert is not None or alert_code is not None:
        return None, "STUDY_RIGHT_SOURCE_MALFORMED"
    expiration_date = risk.get("expiration_date")
    days_until = risk.get("days_until_expiration")
    extension_count = risk.get("extension_count")
    if (
        expiration_date is not None and not isinstance(expiration_date, str)
    ) or (
        days_until is not None
        and (
            not isinstance(days_until, int)
            or isinstance(days_until, bool)
        )
    ) or not _is_nonnegative_int(extension_count):
        return None, "STUDY_RIGHT_SOURCE_MALFORMED"
    return (
        StudyRightAlertSource(
            student_id=student_id,
            alert_code=alert_code,
            risk_status=risk_status,
            requires_attention=attention,
            expiration_date=expiration_date,
            days_until_expiration=days_until,
            extension_count=extension_count,
        ),
        None,
    )


def _risk_results(
    result: RiskDetectionWorkflowResult,
) -> tuple[dict[int, StudentRiskDetectionResult], SourceStatus, list[str]]:
    if not isinstance(result, RiskDetectionWorkflowResult):
        return {}, "failed", ["RISK_DETECTION_RESULT_MALFORMED"]
    if result.status not in {"completed", "partial", "failed"}:
        return {}, "failed", ["RISK_DETECTION_RESULT_MALFORMED"]
    if result.status == "failed":
        return {}, "failed", list(result.errors)
    parsed: dict[int, StudentRiskDetectionResult] = {}
    for item in result.results:
        if not isinstance(item, StudentRiskDetectionResult) or item.student_id in parsed:
            return {}, "failed", ["RISK_DETECTION_RESULT_MALFORMED"]
        parsed[item.student_id] = item
    return parsed, result.status, list(result.errors)


def _source_status(values: list[bool]) -> SourceStatus:
    if not values or all(values):
        return "completed"
    if any(values):
        return "partial"
    return "failed"


def _aggregate_status(statuses: Any) -> AlertGenerationStatus:
    values = list(statuses)
    if values and all(status == "completed" for status in values):
        return "completed"
    if any(status == "completed" for status in values) or any(
        status == "partial" for status in values
    ):
        return "partial"
    return "failed"


def _alert_type_counts(alerts: list[AcademicAlert]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for alert in alerts:
        counts[alert.alert_type] = counts.get(alert.alert_type, 0) + 1
    return dict(sorted(counts.items()))


def _failed_result(
    *,
    generated_at: datetime,
    error: str,
) -> AcademicAlertGenerationResult:
    return AcademicAlertGenerationResult(
        workflow_name=ACADEMIC_ALERT_WORKFLOW_NAME,
        generated_at=generated_at.isoformat(),
        evaluation_date=generated_at.date().isoformat(),
        status="failed",
        students_considered=0,
        alert_count=0,
        alert_type_counts={},
        source_statuses={
            "delayed_progress": "failed",
            "study_right": "failed",
            "overall_risk": "failed",
        },
        errors=[error],
    )


def _validate_input(alert_input: AcademicAlertInput) -> None:
    if alert_input.generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    if alert_input.generated_at.date() != alert_input.evaluation_date:
        raise ValueError("generated_at and evaluation_date must agree")
    if set(alert_input.source_statuses) != {
        "delayed_progress",
        "study_right",
        "overall_risk",
    }:
        raise ValueError("source_statuses must contain every supported source")
    if not all(status in {"completed", "partial", "failed"} for status in alert_input.source_statuses.values()):
        raise ValueError("source_statuses contains an invalid status")
    seen_ids: set[int] = set()
    for student in alert_input.students:
        if not _is_positive_int(student.student_id) or student.student_id in seen_ids:
            raise ValueError("students must have unique positive student IDs")
        seen_ids.add(student.student_id)
        for source in (student.delayed_progress, student.study_right, student.overall_risk):
            if source is not None and source.student_id != student.student_id:
                raise ValueError("source result does not match its affected student")


def _validated_student_ids(values: Any) -> list[int]:
    if not isinstance(values, list) or not all(_is_positive_int(value) for value in values):
        raise ValueError("active student directory returned invalid IDs")
    return sorted(set(values))


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _result_code(result: Any, default: str) -> str:
    if isinstance(result, dict):
        code = result.get("error")
        if isinstance(code, str) and code:
            return code
    return default


def _as_local_datetime(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        raise ValueError("evaluation_time must be timezone-aware")
    return value.astimezone(timezone)


def _load_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        logger.warning("Academic alert timezone %s is unavailable; using UTC", value)
        return ZoneInfo("UTC")


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
