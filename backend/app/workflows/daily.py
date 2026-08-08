"""Deterministic daily orchestration workflow for Issue #102.

The workflow consumes existing event and academic-risk contracts.  It does not
recreate academic business rules, persist workflow executions, render Telegram
messages, resolve recipients, or infer tutor actions from free-text meeting
notes.  It hands the already-generated Issue #106 result to the optional
Issue #107 delivery boundary.
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
from app.services.event_service import EventService
from app.services.scheduler import DailyTimeTrigger, DuplicateJobError, Scheduler
from app.workflows.execution_logging import (
    TriggerType,
    WorkflowExecutionRecorder,
    workflow_outcome,
)


logger = logging.getLogger("academic-copilot.workflows.daily")

DAILY_WORKFLOW_NAME = "academic_daily_workflow"
DAILY_WORKFLOW_JOB_ID = DAILY_WORKFLOW_NAME

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


class AcademicAlertRunner(Protocol):
    def run(
        self,
        *,
        evaluation_time: datetime,
        risk_detection_result: Any,
    ) -> Any: ...


class AcademicAlertDeliveryRunner(Protocol):
    def deliver(self, alert_result: Any) -> Any: ...


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
    academic_alerts: DailyCheckResult
    tutor_notifications: DailyCheckResult
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
        academic_alert_generation: AcademicAlertRunner | None = None,
        academic_alert_delivery: AcademicAlertDeliveryRunner | None = None,
        execution_recorder: WorkflowExecutionRecorder | None = None,
    ) -> None:
        if student_page_size <= 0:
            raise ValueError("student_page_size must be positive")

        self._student_directory = student_directory
        self._event_provider = event_provider
        self._risk_provider = risk_provider
        self._timezone = _load_timezone(timezone)
        self._student_page_size = student_page_size
        self._automatic_risk_detection = automatic_risk_detection
        self._academic_alert_generation = academic_alert_generation
        self._academic_alert_delivery = academic_alert_delivery
        self._execution_recorder = execution_recorder

    def run(
        self,
        *,
        now: datetime | None = None,
        trigger_type: TriggerType = "direct",
    ) -> DailyWorkflowResult:
        """Execute all checks for the current local calendar date.

        ``now`` must be timezone-aware when supplied, making date boundaries
        deterministic in tests and direct invocations.
        """

        if self._execution_recorder is None:
            return self._run(now=now)

        execution_time = _as_local_datetime(now, self._timezone)
        return self._execution_recorder.run(
            workflow_name=DAILY_WORKFLOW_NAME,
            execution_key=f"daily:{execution_time.date().isoformat()}",
            trigger_type=trigger_type,
            operation=lambda: self._run(now=execution_time),
            outcome_for=_daily_execution_outcome,
        )

    def _run(self, *, now: datetime | None = None) -> DailyWorkflowResult:
        """Execute the established daily business workflow without logging policy."""

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
        risk_detection_result: Any | None = None
        if self._automatic_risk_detection is not None:
            student_risks, risk_detection_result = self._check_automatic_risk_detection(
                local_now
            )
        else:
            student_risks = self._check_student_risks(
                execution_date,
                evaluation_time=local_now,
            )
        academic_alerts, alert_result = self._check_academic_alerts(
            evaluation_time=local_now,
            risk_detection_result=risk_detection_result,
        )
        tutor_notifications = self._deliver_academic_alerts(alert_result)
        pending_tutor_actions = _unavailable_tutor_action_check()
        checks = (
            academic_events,
            student_risks,
            academic_alerts,
            tutor_notifications,
            pending_tutor_actions,
        )
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
            academic_alerts=academic_alerts,
            tutor_notifications=tutor_notifications,
            pending_tutor_actions=pending_tutor_actions,
            warnings=warnings,
            errors=errors,
        )
        logger.info(
            "Daily workflow finished: status=%s event_status=%s event_count=%s "
            "risk_status=%s risk_count=%s alert_status=%s alert_count=%s "
            "notification_status=%s notification_count=%s tutor_action_status=%s",
            result.status,
            academic_events.status,
            academic_events.count,
            student_risks.status,
            student_risks.count,
            academic_alerts.status,
            academic_alerts.count,
            tutor_notifications.status,
            tutor_notifications.count,
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
            check, _ = self._check_automatic_risk_detection(evaluation_time)
            return check
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
    ) -> tuple[DailyCheckResult, Any | None]:
        """Adapt the reusable Issue #104 result to the existing daily DTO."""

        try:
            result = self._automatic_risk_detection.run(
                evaluation_time=evaluation_time
            )
        except Exception:
            logger.exception("Daily workflow automatic risk detection failed")
            return (
                DailyCheckResult(
                    name="student_risks",
                    status="failed",
                    count=None,
                    reason_codes=["AUTOMATIC_RISK_DETECTION_FAILED"],
                ),
                None,
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
            return (
                DailyCheckResult(
                    name="student_risks",
                    status="failed",
                    count=None,
                    reason_codes=["AUTOMATIC_RISK_DETECTION_MALFORMED"],
                ),
                None,
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
        return (
            DailyCheckResult(
                name="student_risks",
                status=status,
                count=evaluated_count if status in {"completed", "partial"} else None,
                details=details,
                reason_codes=_deduplicate(errors),
            ),
            result,
        )

    def _check_academic_alerts(
        self,
        *,
        evaluation_time: datetime,
        risk_detection_result: Any | None,
    ) -> tuple[DailyCheckResult, Any | None]:
        if self._academic_alert_generation is None:
            return (
                DailyCheckResult(
                    name="academic_alerts",
                    status="unavailable",
                    count=None,
                    reason_codes=["ACADEMIC_ALERT_WORKFLOW_UNAVAILABLE"],
                ),
                None,
            )
        if risk_detection_result is None:
            return (
                DailyCheckResult(
                    name="academic_alerts",
                    status="unavailable",
                    count=None,
                    reason_codes=["RISK_DETECTION_RESULT_UNAVAILABLE"],
                ),
                None,
            )
        try:
            result = self._academic_alert_generation.run(
                evaluation_time=evaluation_time,
                risk_detection_result=risk_detection_result,
            )
        except Exception:
            logger.exception("Daily workflow academic-alert generation failed")
            return (
                DailyCheckResult(
                    name="academic_alerts",
                    status="failed",
                    count=None,
                    reason_codes=["ACADEMIC_ALERT_GENERATION_FAILED"],
                ),
                None,
            )

        status = getattr(result, "status", None)
        alert_count = getattr(result, "alert_count", None)
        students_considered = getattr(result, "students_considered", None)
        alert_type_counts = getattr(result, "alert_type_counts", None)
        suppressed_count = getattr(result, "suppressed_overall_risk_alert_count", None)
        errors = getattr(result, "errors", None)
        if (
            status not in {"completed", "partial", "failed"}
            or not _is_nonnegative_int(alert_count)
            or not _is_nonnegative_int(students_considered)
            or not isinstance(alert_type_counts, dict)
            or not all(
                isinstance(key, str) and _is_nonnegative_int(value)
                for key, value in alert_type_counts.items()
            )
            or not _is_nonnegative_int(suppressed_count)
            or not isinstance(errors, list)
            or not all(isinstance(error, str) for error in errors)
        ):
            return (
                DailyCheckResult(
                    name="academic_alerts",
                    status="failed",
                    count=None,
                    reason_codes=["ACADEMIC_ALERT_GENERATION_MALFORMED"],
                ),
                None,
            )
        return (
            DailyCheckResult(
                name="academic_alerts",
                status=status,
                count=alert_count if status in {"completed", "partial"} else None,
                details={
                    "students_considered": students_considered,
                    "delayed_progress_alerts": _alert_type_count(
                        alert_type_counts,
                        "DELAYED_PROGRESS",
                    ),
                    "study_right_alerts": sum(
                        _alert_type_count(alert_type_counts, alert_type)
                        for alert_type in (
                            "STUDY_RIGHT_EXPIRED",
                            "STUDY_RIGHT_EXPIRING_SOON",
                            "STUDY_RIGHT_EXTENDED",
                        )
                    ),
                    "overall_risk_alerts": _alert_type_count(
                        alert_type_counts,
                        "ACADEMIC_RISK_DETECTED",
                    ),
                    "suppressed_overall_risk_alerts": suppressed_count,
                },
                reason_codes=_deduplicate(errors),
            ),
            result,
        )

    def _deliver_academic_alerts(self, alert_result: Any | None) -> DailyCheckResult:
        """Deliver the exact #106 result without reconstructing academic facts."""

        if self._academic_alert_delivery is None:
            return DailyCheckResult(
                name="tutor_notifications",
                status="unavailable",
                count=None,
                reason_codes=["TELEGRAM_NOTIFICATION_DELIVERY_UNAVAILABLE"],
            )
        if alert_result is None:
            return DailyCheckResult(
                name="tutor_notifications",
                status="unavailable",
                count=None,
                reason_codes=["ACADEMIC_ALERT_RESULT_UNAVAILABLE"],
            )
        try:
            result = self._academic_alert_delivery.deliver(alert_result)
        except Exception:
            logger.exception("Daily workflow Telegram notification delivery failed")
            return DailyCheckResult(
                name="tutor_notifications",
                status="failed",
                count=None,
                reason_codes=["TELEGRAM_NOTIFICATION_DELIVERY_FAILED"],
            )

        status = getattr(result, "status", None)
        attempted_count = getattr(result, "attempted_count", None)
        delivered_count = getattr(result, "delivered_count", None)
        failed_count = getattr(result, "failed_count", None)
        skipped_count = getattr(result, "skipped_count", None)
        errors = getattr(result, "errors", None)
        if (
            status not in {"completed", "partial", "failed"}
            or not _is_nonnegative_int(attempted_count)
            or not _is_nonnegative_int(delivered_count)
            or not _is_nonnegative_int(failed_count)
            or not _is_nonnegative_int(skipped_count)
            or attempted_count != delivered_count + failed_count
            or not isinstance(errors, list)
            or not all(isinstance(error, str) for error in errors)
        ):
            return DailyCheckResult(
                name="tutor_notifications",
                status="failed",
                count=None,
                reason_codes=["TELEGRAM_NOTIFICATION_DELIVERY_MALFORMED"],
            )
        return DailyCheckResult(
            name="tutor_notifications",
            status=status,
            count=delivered_count if status in {"completed", "partial"} else None,
            details={
                "attempted_notifications": attempted_count,
                "delivered_notifications": delivered_count,
                "failed_notifications": failed_count,
                "skipped_notifications": skipped_count,
            },
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
    from app.repositories.workflow_execution_log_repository import (
        WorkflowExecutionLogRepository,
    )
    from app.workflows.automatic_risk_detection import (
        create_database_automatic_risk_detection_workflow,
    )
    from app.workflows.academic_alerts import create_database_academic_alert_workflow
    from app.telegram.notifications import (
        create_database_academic_alert_notification_delivery,
    )

    execution_recorder = WorkflowExecutionRecorder(
        WorkflowExecutionLogRepository(session)
    )
    automatic_risk_detection = create_database_automatic_risk_detection_workflow(
        session=session,
        timezone=timezone,
        execution_recorder=execution_recorder,
    )
    return DailyWorkflow(
        event_provider=event_service,
        timezone=timezone,
        automatic_risk_detection=automatic_risk_detection,
        academic_alert_generation=create_database_academic_alert_workflow(
            session=session,
            timezone=timezone,
            execution_recorder=execution_recorder,
        ),
        academic_alert_delivery=create_database_academic_alert_notification_delivery(
            session=session,
            execution_recorder=execution_recorder,
        ),
        execution_recorder=execution_recorder,
    )


def run_scheduled_daily_workflow() -> DailyWorkflowResult:
    """Run from the scheduler with a short-lived database session."""

    session = SessionLocal()
    try:
        workflow = create_database_daily_workflow(
            session=session,
            timezone=settings.daily_workflow_timezone,
        )
        return workflow.run(trigger_type="scheduler")
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


def _daily_execution_outcome(result: DailyWorkflowResult):
    checks = (
        result.academic_events,
        result.student_risks,
        result.academic_alerts,
        result.tutor_notifications,
        result.pending_tutor_actions,
    )
    return workflow_outcome(
        status=result.status,
        requested_count=len(checks),
        processed_count=sum(
            check.status in {"completed", "partial", "failed"}
            for check in checks
        ),
        succeeded_count=sum(check.status == "completed" for check in checks),
        failed_count=sum(check.status == "failed" for check in checks),
        skipped_count=0,
        warnings=result.warnings,
        errors=result.errors,
    )


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


def _alert_type_count(alert_type_counts: dict[str, Any], alert_type: str) -> int:
    value = alert_type_counts.get(alert_type, 0)
    return value if _is_nonnegative_int(value) else 0


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
