"""Reusable automatic risk detection for Issue #104.

This workflow owns batch orchestration only. It consumes the canonical Issue
#95 scorer in its explicit partial-level mode, evaluates only ACTIVE students,
and returns a serializable, non-identifying result that callers and AI agents
can consume without FastAPI, a scheduler, or conversation state.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.db.database import SessionLocal
from app.repositories.event_repository import EventRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.repositories.tutor_meeting_repository import TutorMeetingRepository
from app.services.academic_risk_scoring_service import AcademicRiskScoringService
from app.services.delay_detection_service import DelayDetectionService
from app.services.event_service import EventService
from app.services.progress_service import ProgressService
from app.services.student_service import StudentService
from app.services.study_right_risk_service import StudyRightRiskService
from app.services.study_right_service import StudyRightService
from app.services.tutor_meeting_risk_service import TutorMeetingRiskService
from app.workflows.execution_logging import (
    TriggerType,
    WorkflowExecutionRecorder,
    workflow_outcome,
)


logger = logging.getLogger("academic-copilot.workflows.automatic_risk_detection")

AUTOMATIC_RISK_DETECTION_WORKFLOW_NAME = "automatic_risk_detection"
CANONICAL_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
TUTOR_ATTENTION_RISK_LEVELS = frozenset({"MEDIUM", "HIGH", "CRITICAL"})

WorkflowStatus = Literal["completed", "partial", "failed"]
AssessmentStatus = Literal["COMPLETE", "PARTIAL"]


class ActiveStudentDirectory(Protocol):
    def list_active_student_ids(
        self,
        student_ids: Sequence[int] | None = None,
    ) -> list[int]: ...


class RiskProvider(Protocol):
    def assess_student_risk(
        self,
        student_id: int,
        *,
        as_of_date: date,
        allow_partial_risk_level: bool = False,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class StudentRiskDetectionResult:
    """Non-identifying canonical risk result for one active student."""

    student_id: int
    risk_level: str
    risk_score: int
    assessment_status: AssessmentStatus
    requires_tutor_attention: bool
    contributing_indicators: list[str]
    unavailable_indicators: list[str]
    score_basis: str
    policy_version: str
    actionable_indicators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskDetectionWorkflowResult:
    """Aggregate result from one deterministic active-student evaluation."""

    workflow_name: str
    execution_key: str
    evaluated_at: str
    status: WorkflowStatus
    active_student_count: int
    evaluated_student_count: int
    at_risk_student_count: int
    risk_level_counts: dict[str, int]
    results: list[StudentRiskDetectionResult] = field(default_factory=list)
    unavailable_indicator_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "results": [result.to_dict() for result in self.results],
        }


class AutomaticRiskDetectionWorkflow:
    """Evaluate ACTIVE students using the approved canonical risk policy."""

    def __init__(
        self,
        *,
        active_student_directory: ActiveStudentDirectory,
        risk_provider: RiskProvider,
        timezone: str,
        execution_recorder: WorkflowExecutionRecorder | None = None,
    ) -> None:
        self._active_student_directory = active_student_directory
        self._risk_provider = risk_provider
        self._timezone = _load_timezone(timezone)
        self._execution_recorder = execution_recorder

    def run(
        self,
        *,
        evaluation_time: datetime | None = None,
        student_ids: Sequence[int] | None = None,
        trigger_type: TriggerType = "direct",
    ) -> RiskDetectionWorkflowResult:
        """Run directly for all ACTIVE students or an active subset.

        Explicit IDs are always intersected with the active-student repository
        filter. Inactive students are never evaluated by this workflow.
        """

        if self._execution_recorder is None:
            return self._run(
                evaluation_time=evaluation_time,
                student_ids=student_ids,
            )

        local_time = _as_local_datetime(evaluation_time, self._timezone)
        return self._execution_recorder.run(
            workflow_name=AUTOMATIC_RISK_DETECTION_WORKFLOW_NAME,
            execution_key=f"risk-detection:{local_time.date().isoformat()}",
            trigger_type=trigger_type,
            operation=lambda: self._run(
                evaluation_time=local_time,
                student_ids=student_ids,
            ),
            outcome_for=_risk_detection_execution_outcome,
        )

    def _run(
        self,
        *,
        evaluation_time: datetime | None = None,
        student_ids: Sequence[int] | None = None,
    ) -> RiskDetectionWorkflowResult:
        """Execute established risk orchestration without logging policy."""

        local_time = _as_local_datetime(evaluation_time, self._timezone)
        evaluation_date = local_time.date()
        execution_key = f"risk-detection:{evaluation_date.isoformat()}"
        logger.info("Automatic risk detection started: execution_key=%s", execution_key)

        try:
            active_student_ids = _validated_sorted_ids(
                self._active_student_directory.list_active_student_ids(student_ids)
            )
        except Exception:
            logger.exception("Automatic risk detection could not list active students")
            return RiskDetectionWorkflowResult(
                workflow_name=AUTOMATIC_RISK_DETECTION_WORKFLOW_NAME,
                execution_key=execution_key,
                evaluated_at=local_time.isoformat(),
                status="failed",
                active_student_count=0,
                evaluated_student_count=0,
                at_risk_student_count=0,
                risk_level_counts=_empty_risk_level_counts(),
                errors=["ACTIVE_STUDENT_DIRECTORY_UNAVAILABLE"],
            )

        if not active_student_ids:
            return self._result(
                execution_key=execution_key,
                evaluated_at=local_time,
                active_student_count=0,
                evaluated_student_count=0,
                partial_assessments=0,
                unavailable_assessments=0,
                failed_assessments=0,
                risk_level_counts=_empty_risk_level_counts(),
                results=[],
                unavailable_indicator_counts={},
                errors=[],
            )

        evaluated = partial = unavailable = failed = 0
        risk_level_counts = _empty_risk_level_counts()
        results: list[StudentRiskDetectionResult] = []
        unavailable_indicator_counts: dict[str, int] = {}
        errors: list[str] = []

        for student_id in active_student_ids:
            try:
                assessment = self._risk_provider.assess_student_risk(
                    student_id,
                    as_of_date=evaluation_date,
                    allow_partial_risk_level=True,
                )
            except Exception:
                logger.exception("Automatic risk detection assessment failed")
                failed += 1
                errors.append("RISK_ASSESSMENT_FAILED")
                continue

            parsed = _parse_assessment(assessment)
            if isinstance(parsed, str):
                unavailable += 1
                errors.append(parsed)
                continue

            evaluated += 1
            if parsed.assessment_status == "PARTIAL":
                partial += 1
            risk_level_counts[parsed.risk_level] += 1
            for indicator in parsed.unavailable_indicators:
                unavailable_indicator_counts[indicator] = (
                    unavailable_indicator_counts.get(indicator, 0) + 1
                )
            if parsed.requires_tutor_attention:
                results.append(parsed)

        result = self._result(
            execution_key=execution_key,
            evaluated_at=local_time,
            active_student_count=len(active_student_ids),
            evaluated_student_count=evaluated,
            partial_assessments=partial,
            unavailable_assessments=unavailable,
            failed_assessments=failed,
            risk_level_counts=risk_level_counts,
            results=sorted(results, key=_attention_sort_key),
            unavailable_indicator_counts=unavailable_indicator_counts,
            errors=_deduplicate(errors),
        )
        logger.info(
            "Automatic risk detection finished: status=%s active_count=%s "
            "evaluated_count=%s attention_count=%s partial_count=%s",
            result.status,
            result.active_student_count,
            result.evaluated_student_count,
            result.at_risk_student_count,
            partial,
        )
        return result

    def _result(
        self,
        *,
        execution_key: str,
        evaluated_at: datetime,
        active_student_count: int,
        evaluated_student_count: int,
        partial_assessments: int,
        unavailable_assessments: int,
        failed_assessments: int,
        risk_level_counts: dict[str, int],
        results: list[StudentRiskDetectionResult],
        unavailable_indicator_counts: dict[str, int],
        errors: list[str],
    ) -> RiskDetectionWorkflowResult:
        if evaluated_student_count == 0 and (unavailable_assessments or failed_assessments):
            status: WorkflowStatus = "failed"
        elif partial_assessments or unavailable_assessments or failed_assessments:
            status = "partial"
        else:
            status = "completed"

        warnings: list[str] = []
        if partial_assessments:
            warnings.append(
                "Partial assessments have normalized canonical scores and explicitly list unavailable indicators."
            )
        if unavailable_assessments:
            warnings.append(
                "Some active students could not receive a canonical risk result."
            )

        return RiskDetectionWorkflowResult(
            workflow_name=AUTOMATIC_RISK_DETECTION_WORKFLOW_NAME,
            execution_key=execution_key,
            evaluated_at=evaluated_at.isoformat(),
            status=status,
            active_student_count=active_student_count,
            evaluated_student_count=evaluated_student_count,
            at_risk_student_count=len(results),
            risk_level_counts=risk_level_counts,
            results=results,
            unavailable_indicator_counts=dict(sorted(unavailable_indicator_counts.items())),
            warnings=warnings,
            errors=errors,
        )


def create_database_automatic_risk_detection_workflow(
    *,
    session: Any,
    timezone: str,
    execution_recorder: WorkflowExecutionRecorder | None = None,
) -> AutomaticRiskDetectionWorkflow:
    """Wire the reusable workflow to the existing authoritative services."""

    student_repository = StudentRepository(session)
    progress_service = ProgressService(ProgressRepository(session))
    student_service = StudentService(student_repository)
    study_right_service = StudyRightService(StudyRightRepository(session))
    event_service = EventService(EventRepository(session))
    risk_service = AcademicRiskScoringService(
        DelayDetectionService(progress_service),
        StudyRightRiskService(study_right_service, student_service),
        event_service,
        TutorMeetingRiskService(TutorMeetingRepository(session)),
    )
    return AutomaticRiskDetectionWorkflow(
        active_student_directory=student_repository,
        risk_provider=risk_service,
        timezone=timezone,
        execution_recorder=execution_recorder,
    )


def run_database_automatic_risk_detection(
    *,
    evaluation_time: datetime | None = None,
    student_ids: Sequence[int] | None = None,
) -> RiskDetectionWorkflowResult:
    """Agent-safe convenience entry point with a short-lived DB session."""

    session = SessionLocal()
    try:
        from app.repositories.workflow_execution_log_repository import (
            WorkflowExecutionLogRepository,
        )

        workflow = create_database_automatic_risk_detection_workflow(
            session=session,
            timezone=settings.daily_workflow_timezone,
            execution_recorder=WorkflowExecutionRecorder(
                WorkflowExecutionLogRepository(session)
            ),
        )
        return workflow.run(
            evaluation_time=evaluation_time,
            student_ids=student_ids,
        )
    finally:
        session.close()


def _parse_assessment(value: Any) -> StudentRiskDetectionResult | str:
    if not isinstance(value, dict) or value.get("success") is not True:
        return _result_code(value, "RISK_ASSESSMENT_UNAVAILABLE")
    student_id = value.get("student_id")
    risk_level = value.get("risk_level")
    risk_score = value.get("score")
    assessment_status = value.get("assessment_status")
    score_basis = value.get("score_basis")
    policy_version = value.get("policy_version")
    contributions = value.get("indicator_contributions")
    unavailable = value.get("unavailable_indicators")
    if (
        not _is_valid_student_id(student_id)
        or risk_level not in CANONICAL_RISK_LEVELS
        or not _is_valid_score(risk_score)
        or assessment_status not in {"COMPLETE", "PARTIAL"}
        or not isinstance(score_basis, str)
        or not score_basis
        or not isinstance(policy_version, str)
        or not policy_version
        or not isinstance(contributions, list)
        or not isinstance(unavailable, list)
    ):
        return "CANONICAL_RISK_ASSESSMENT_MALFORMED"
    indicator_codes = [
        item.get("indicator_code")
        for item in contributions
        if isinstance(item, dict) and isinstance(item.get("indicator_code"), str)
    ]
    actionable_codes = [
        item.get("indicator_code")
        for item in contributions
        if isinstance(item, dict)
        and isinstance(item.get("indicator_code"), str)
        and isinstance(item.get("assigned_points"), int)
        and not isinstance(item.get("assigned_points"), bool)
        and item["assigned_points"] > 0
    ]
    unavailable_codes = [item for item in unavailable if isinstance(item, str)]
    if len(indicator_codes) != len(contributions) or len(unavailable_codes) != len(unavailable):
        return "CANONICAL_RISK_ASSESSMENT_MALFORMED"
    return StudentRiskDetectionResult(
        student_id=student_id,
        risk_level=risk_level,
        risk_score=risk_score,
        assessment_status=assessment_status,
        requires_tutor_attention=risk_level in TUTOR_ATTENTION_RISK_LEVELS,
        contributing_indicators=indicator_codes,
        unavailable_indicators=unavailable_codes,
        score_basis=score_basis,
        policy_version=policy_version,
        actionable_indicators=actionable_codes,
    )


def _risk_detection_execution_outcome(result: RiskDetectionWorkflowResult):
    return workflow_outcome(
        status=result.status,
        requested_count=result.active_student_count,
        processed_count=result.evaluated_student_count,
        succeeded_count=result.evaluated_student_count,
        failed_count=None,
        skipped_count=0,
        warnings=result.warnings,
        errors=result.errors,
    )


def _empty_risk_level_counts() -> dict[str, int]:
    return {level: 0 for level in CANONICAL_RISK_LEVELS}


def _attention_sort_key(result: StudentRiskDetectionResult) -> tuple[int, int]:
    severity = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    return severity[result.risk_level], result.student_id


def _validated_sorted_ids(values: Any) -> list[int]:
    if not isinstance(values, list):
        raise ValueError("Active student directory returned invalid IDs")
    if not all(_is_valid_student_id(value) for value in values):
        raise ValueError("Active student directory returned invalid IDs")
    return sorted(set(values))


def _as_local_datetime(value: datetime | None, timezone: ZoneInfo) -> datetime:
    if value is None:
        return datetime.now(timezone)
    if value.tzinfo is None:
        raise ValueError("evaluation_time must be timezone-aware")
    return value.astimezone(timezone)


def _load_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        logger.warning("Automatic risk detection timezone %s is unavailable; using UTC", value)
        return ZoneInfo("UTC")


def _result_code(result: Any, default: str) -> str:
    if isinstance(result, dict):
        code = result.get("error")
        if isinstance(code, str) and code:
            return code
    return default


def _is_valid_student_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_valid_score(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
