"""Deterministic daily orchestration workflow for Issue #102.

The workflow consumes existing event and academic-risk contracts.  It does not
recreate academic business rules, persist workflow executions, send Telegram
messages, or infer tutor actions from free-text meeting notes.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.db.database import SessionLocal
from app.repositories.event_repository import EventRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.services.academic_risk_scoring_service import AcademicRiskScoringService
from app.services.delay_detection_service import DelayDetectionService
from app.services.event_service import EventService
from app.services.progress_service import ProgressService
from app.services.scheduler import DailyTimeTrigger, DuplicateJobError, Scheduler
from app.services.student_service import StudentService
from app.services.study_right_risk_service import StudyRightRiskService
from app.services.study_right_service import StudyRightService


logger = logging.getLogger("academic-copilot.workflows.daily")

DAILY_WORKFLOW_JOB_ID = "academic_daily_workflow"

CheckStatus = Literal["completed", "partial", "failed", "unavailable"]
WorkflowStatus = Literal["completed", "partial", "failed", "unavailable"]


class EventProvider(Protocol):
    def get_upcoming_events(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]: ...


class RiskProvider(Protocol):
    def assess_student_risk(
        self, student_id: int, *, as_of_date: date
    ) -> dict[str, Any]: ...


class StudentDirectory(Protocol):
    def search_students(
        self,
        query: str | None = None,
        programme_code: str | None = None,
        group_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]: ...


class RiskDetectionRunner(Protocol):
    def run(self, *, evaluation_time: datetime | None = None) -> Any: ...


@dataclass(frozen=True)
class DailyCheckResult:
    """Aggregate result for one independent daily check.

    ``count`` is zero only after a successful completed check.  It is ``None``
    when the check was unavailable or failed, preventing missing data from being
    presented as an empty result.
    """

    name: str
    status: CheckStatus
    count: int | None
    details: dict[str, int] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DailyWorkflowResult:
    """Typed, non-persistent aggregate from one daily workflow execution."""

    status: WorkflowStatus
    generated_at: str
    execution_date: str
    execution_key: str
    academic_events: DailyCheckResult
    student_risks: DailyCheckResult
    pending_tutor_actions: DailyCheckResult
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DailyWorkflow:
    """Run existing daily checks without adding new academic decisions."""

    def __init__(
        self,
        *,
        student_directory: StudentDirectory | None = None,
        event_provider: EventProvider,
        risk_provider: RiskProvider | None = None,
        timezone: str,
        student_page_size: int = 100,
        automatic_risk_detection: RiskDetectionRunner | None = None,
    ) -> None:
        if student_page_size <= 0:
            raise ValueError("student_page_size must be positive")

        self._student_directory = student_directory
        self._event_provider = event_provider
        self._risk_provider = risk_provider
        self._timezone = _load_timezone(timezone)
        self._student_page_size = student_page_size
        self._automatic_risk_detection = automatic_risk_detection

    def run(self, *, now: datetime | None = None) -> DailyWorkflowResult:
        """Execute all checks for the current local calendar date.

        ``now`` must be timezone-aware when supplied, making date boundaries
        deterministic in tests and direct invocations.
        """

        local_now = _as_local_datetime(now, self._timezone)
        execution_date = local_now.date()
        generated_at = local_now.isoformat()
        execution_key = f"daily:{execution_date.isoformat()}"

        logger.info(
            "Daily workflow started: execution_date=%s execution_key=%s",
            execution_date.isoformat(),
            execution_key,
        )

        academic_events = self._check_academic_events(execution_date)
        student_risks = self._check_student_risks(
            execution_date,
            evaluation_time=local_now,
        )
        pending_tutor_actions = _unavailable_tutor_action_check()
        checks = (academic_events, student_risks, pending_tutor_actions)
        status = _aggregate_status(checks)

        warnings = [
            "Pending tutor actions are unavailable because no structured tutor-action contract exists."
        ]
        errors = [
            f"{check.name}:{code}"
            for check in checks
            if check.status == "failed"
            for code in check.reason_codes
        ]
        result = DailyWorkflowResult(
            status=status,
            generated_at=generated_at,
            execution_date=execution_date.isoformat(),
            execution_key=execution_key,
            academic_events=academic_events,
            student_risks=student_risks,
            pending_tutor_actions=pending_tutor_actions,
            warnings=warnings,
            errors=errors,
        )
        logger.info(
            "Daily workflow finished: status=%s event_status=%s event_count=%s "
            "risk_status=%s risk_count=%s tutor_action_status=%s",
            result.status,
            academic_events.status,
            academic_events.count,
            student_risks.status,
            student_risks.count,
            pending_tutor_actions.status,
        )
        return result

    def _check_academic_events(self, execution_date: date) -> DailyCheckResult:
        try:
            result = self._event_provider.get_upcoming_events(
                start_date=execution_date.isoformat(),
                end_date=execution_date.isoformat(),
            )
        except Exception:
            logger.exception("Daily workflow academic-event check failed")
            return DailyCheckResult(
                name="academic_events",
                status="failed",
                count=None,
                reason_codes=["ACADEMIC_EVENTS_CHECK_FAILED"],
            )

        if not isinstance(result, dict) or result.get("success") is not True:
            return DailyCheckResult(
                name="academic_events",
                status="unavailable",
                count=None,
                reason_codes=[_result_code(result, "ACADEMIC_EVENTS_UNAVAILABLE")],
            )

        events = result.get("events")
        if not isinstance(events, list):
            return DailyCheckResult(
                name="academic_events",
                status="unavailable",
                count=None,
                reason_codes=["ACADEMIC_EVENTS_MALFORMED"],
            )

        return DailyCheckResult(
            name="academic_events",
            status="completed",
            count=len(events),
            details={"events_found": len(events)},
        )

    def _check_student_risks(
        self,
        execution_date: date,
        *,
        evaluation_time: datetime,
    ) -> DailyCheckResult:
        if self._automatic_risk_detection is not None:
            return self._check_automatic_risk_detection(evaluation_time)
        if self._student_directory is None or self._risk_provider is None:
            return DailyCheckResult(
                name="student_risks",
                status="failed",
                count=None,
                reason_codes=["RISK_DETECTION_WORKFLOW_UNAVAILABLE"],
            )
        try:
            students = self._list_students()
        except Exception:
            logger.exception("Daily workflow student-risk check could not list students")
            return DailyCheckResult(
                name="student_risks",
                status="failed",
                count=None,
                reason_codes=["STUDENT_DIRECTORY_CHECK_FAILED"],
            )

        if not students:
            return DailyCheckResult(
                name="student_risks",
                status="completed",
                count=0,
                details={"students_discovered": 0, "students_assessed": 0},
            )

        assessed = 0
        partial_assessments = 0
        unavailable_assessments = 0
        failed_assessments = 0
        reason_codes: list[str] = []

        for student in students:
            student_id = student.get("id") if isinstance(student, dict) else None
            if not _is_valid_student_id(student_id):
                failed_assessments += 1
                reason_codes.append("STUDENT_RECORD_MALFORMED")
                continue

            try:
                result = self._risk_provider.assess_student_risk(
                    student_id,
                    as_of_date=execution_date,
                )
            except Exception:
                logger.exception("Daily workflow student-risk assessment failed")
                failed_assessments += 1
                reason_codes.append("STUDENT_RISK_CHECK_FAILED")
                continue

            if not isinstance(result, dict) or result.get("success") is not True:
                unavailable_assessments += 1
                reason_codes.append(_result_code(result, "STUDENT_RISK_UNAVAILABLE"))
                continue

            assessment_status = result.get("assessment_status")
            if assessment_status not in {"COMPLETE", "PARTIAL"}:
                failed_assessments += 1
                reason_codes.append("STUDENT_RISK_MALFORMED")
                continue

            assessed += 1
            if assessment_status == "PARTIAL":
                partial_assessments += 1

        details = {
            "students_discovered": len(students),
            "students_assessed": assessed,
            "partial_assessments": partial_assessments,
            "unavailable_assessments": unavailable_assessments,
            "failed_assessments": failed_assessments,
        }
        if assessed == len(students) and partial_assessments == 0:
            status: CheckStatus = "completed"
        elif assessed:
            status = "partial"
        elif failed_assessments:
            status = "failed"
        else:
            status = "unavailable"

        return DailyCheckResult(
            name="student_risks",
            status=status,
            count=assessed if status in {"completed", "partial"} else None,
            details=details,
            reason_codes=_deduplicate(reason_codes),
        )

    def _check_automatic_risk_detection(
        self,
        evaluation_time: datetime,
    ) -> DailyCheckResult:
        """Adapt the reusable Issue #104 result to the existing daily DTO."""

        try:
            result = self._automatic_risk_detection.run(
                evaluation_time=evaluation_time
            )
        except Exception:
            logger.exception("Daily workflow automatic risk detection failed")
            return DailyCheckResult(
                name="student_risks",
                status="failed",
                count=None,
                reason_codes=["AUTOMATIC_RISK_DETECTION_FAILED"],
            )

        status = getattr(result, "status", None)
        active_count = getattr(result, "active_student_count", None)
        evaluated_count = getattr(result, "evaluated_student_count", None)
        attention_count = getattr(result, "at_risk_student_count", None)
        level_counts = getattr(result, "risk_level_counts", None)
        errors = getattr(result, "errors", None)
        if (
            status not in {"completed", "partial", "failed"}
            or not _is_nonnegative_int(active_count)
            or not _is_nonnegative_int(evaluated_count)
            or not _is_nonnegative_int(attention_count)
            or not isinstance(level_counts, dict)
            or not isinstance(errors, list)
            or not all(isinstance(error, str) for error in errors)
        ):
            return DailyCheckResult(
                name="student_risks",
                status="failed",
                count=None,
                reason_codes=["AUTOMATIC_RISK_DETECTION_MALFORMED"],
            )
        details = {
            "active_students_discovered": active_count,
            "students_assessed": evaluated_count,
            "students_requiring_tutor_attention": attention_count,
            "low_risk_students": _risk_level_count(level_counts, "LOW"),
            "medium_risk_students": _risk_level_count(level_counts, "MEDIUM"),
            "high_risk_students": _risk_level_count(level_counts, "HIGH"),
            "critical_risk_students": _risk_level_count(level_counts, "CRITICAL"),
        }
        return DailyCheckResult(
            name="student_risks",
            status=status,
            count=evaluated_count if status in {"completed", "partial"} else None,
            details=details,
            reason_codes=_deduplicate(errors),
        )

    def _list_students(self) -> list[dict[str, Any]]:
        """Read every page through the existing student-directory contract.

        The repository has no defined active-student filter, so this method does
        not invent one.  It processes exactly the directory rows it receives.
        """

        students: list[dict[str, Any]] = []
        offset = 0
        expected_total: int | None = None

        while expected_total is None or offset < expected_total:
            page, total = self._student_directory.search_students(
                limit=self._student_page_size,
                offset=offset,
            )
            if not isinstance(page, list) or not isinstance(total, int) or total < 0:
                raise ValueError("Student directory returned an invalid page")
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise ValueError("Student directory total changed during daily workflow")

            if not page:
                if offset < expected_total:
                    raise ValueError("Student directory ended before its reported total")
                break

            students.extend(page)
            offset += len(page)
            if offset > expected_total:
                raise ValueError("Student directory exceeded its reported total")

        return students


def create_database_daily_workflow(*, session: Any, timezone: str) -> DailyWorkflow:
    """Wire the daily workflow to existing repositories and services."""

    event_service = EventService(EventRepository(session))
    from app.workflows.automatic_risk_detection import (
        create_database_automatic_risk_detection_workflow,
    )
    return DailyWorkflow(
        event_provider=event_service,
        timezone=timezone,
        automatic_risk_detection=create_database_automatic_risk_detection_workflow(
            session=session,
            timezone=timezone,
        ),
    )


def run_scheduled_daily_workflow() -> DailyWorkflowResult:
    """Run from the scheduler with a short-lived database session."""

    session = SessionLocal()
    try:
        workflow = create_database_daily_workflow(
            session=session,
            timezone=settings.daily_workflow_timezone,
        )
        return workflow.run()
    finally:
        session.close()


async def register_daily_workflow(
    scheduler: Scheduler,
    *,
    job: Callable[[], Any] | None = None,
    hour: int | None = None,
    minute: int | None = None,
    timezone: str | None = None,
) -> bool:
    """Register one daily workflow job on the existing scheduler."""

    configured_timezone = timezone or settings.daily_workflow_timezone
    trigger = DailyTimeTrigger(
        hour=settings.daily_workflow_hour if hour is None else hour,
        minute=settings.daily_workflow_minute if minute is None else minute,
        tz=_load_timezone(configured_timezone),
    )
    try:
        await scheduler.register_job(
            DAILY_WORKFLOW_JOB_ID,
            job or run_scheduled_daily_workflow,
            trigger,
        )
    except DuplicateJobError:
        logger.info("Daily workflow job is already registered")
        return False

    logger.info(
        "Daily workflow job registered: job_id=%s time=%02d:%02d timezone=%s",
        DAILY_WORKFLOW_JOB_ID,
        trigger.hour,
        trigger.minute,
        configured_timezone,
    )
    return True


def _unavailable_tutor_action_check() -> DailyCheckResult:
    return DailyCheckResult(
        name="pending_tutor_actions",
        status="unavailable",
        count=None,
        reason_codes=["TUTOR_ACTION_CONTRACT_UNAVAILABLE"],
    )


def _aggregate_status(checks: tuple[DailyCheckResult, ...]) -> WorkflowStatus:
    statuses = {check.status for check in checks}
    if statuses == {"completed"}:
        return "completed"
    if statuses == {"unavailable"}:
        return "unavailable"
    if "completed" in statuses or "partial" in statuses:
        return "partial"
    if "failed" in statuses:
        return "failed"
    return "unavailable"


def _as_local_datetime(value: datetime | None, timezone: ZoneInfo) -> datetime:
    if value is None:
        return datetime.now(timezone)
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(timezone)


def _load_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        logger.warning("Daily workflow timezone %s is unavailable; using UTC", value)
        return ZoneInfo("UTC")


def _result_code(result: Any, default: str) -> str:
    if isinstance(result, dict):
        code = result.get("error")
        if isinstance(code, str) and code:
            return code
    return default


def _is_valid_student_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _risk_level_count(level_counts: dict[str, Any], level: str) -> int:
    value = level_counts.get(level, 0)
    return value if _is_nonnegative_int(value) else 0


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
