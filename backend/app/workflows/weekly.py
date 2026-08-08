"""Aggregate weekly academic reporting workflow for Issue #103.

The workflow reuses existing event, ECTS analytics, and academic-risk services.
It creates one system-wide report for the tutor audience; Issue #101 remains
responsible for per-tutor Monday briefings and no message is delivered here.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any, Callable, Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.db.database import SessionLocal
from app.repositories.event_repository import EventRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.repositories.tutor_meeting_repository import TutorMeetingRepository
from app.repositories.weekly_report_repository import WeeklyReportRepository
from app.services.academic_risk_scoring_service import AcademicRiskScoringService
from app.services.delay_detection_service import DelayDetectionService
from app.services.ects_analytics_service import EctsAnalyticsService
from app.services.event_service import EventService
from app.services.progress_service import ProgressService
from app.services.scheduler import DailyTimeTrigger, DuplicateJobError, Scheduler
from app.services.student_service import StudentService
from app.services.study_right_risk_service import StudyRightRiskService
from app.services.study_right_service import StudyRightService
from app.services.tutor_meeting_risk_service import TutorMeetingRiskService
from app.workflows.execution_logging import (
    TriggerType,
    WorkflowExecutionRecorder,
    workflow_outcome,
)


logger = logging.getLogger("academic-copilot.workflows.weekly")

WEEKLY_WORKFLOW_NAME = "academic_weekly_workflow"
WEEKLY_WORKFLOW_JOB_ID = WEEKLY_WORKFLOW_NAME
MONDAY_WEEKDAY = 0

SectionStatus = Literal["completed", "partial", "failed", "unavailable"]
WorkflowStatus = Literal["completed", "partial", "failed", "unavailable"]
PersistenceStatus = Literal["not_attempted", "saved", "already_stored", "failed"]


class StudentDirectory(Protocol):
    def search_students(
        self,
        query: str | None = None,
        programme_code: str | None = None,
        group_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]: ...


class EventProvider(Protocol):
    def get_upcoming_events(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]: ...


class EctsAnalyticsProvider(Protocol):
    def calculate_ects_for_cohort(self, student_ids: list[int]) -> dict[str, Any]: ...


class RiskProvider(Protocol):
    def assess_student_risk(
        self, student_id: int, *, as_of_date: date
    ) -> dict[str, Any]: ...


class WeeklyReportStore(Protocol):
    def save_report(
        self,
        *,
        workflow_name: str,
        execution_key: str,
        period_start: date,
        period_end: date,
        started_at: datetime,
        completed_at: datetime,
        status: str,
        report_payload: dict[str, Any],
    ) -> dict[str, int | str]: ...


class _ReportScopedEventProvider:
    """Memoize identical event queries while one weekly report is running."""

    def __init__(self, provider: EventProvider) -> None:
        self._provider = provider
        self._results: dict[tuple[str | None, str | None], dict[str, Any]] = {}

    def get_upcoming_events(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]:
        key = (start_date, end_date)
        if key not in self._results:
            self._results[key] = self._provider.get_upcoming_events(
                start_date=start_date,
                end_date=end_date,
            )
        return self._results[key]


@dataclass(frozen=True)
class WeeklyReportSection:
    """A non-identifying aggregate report section."""

    name: str
    status: SectionStatus
    count: int | None
    details: dict[str, int | float] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WeeklyWorkflowResult:
    """Typed, persistable result of one previous-completed-week execution."""

    workflow_name: str
    execution_key: str
    period_start: str
    period_end: str
    started_at: str
    completed_at: str
    status: WorkflowStatus
    sections: list[WeeklyReportSection]
    aggregate_metrics: dict[str, int | float]
    analytics: dict[str, Any]
    persistence_status: PersistenceStatus
    report_id: int | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WeeklyWorkflow:
    """Generate and persist one aggregate report for the previous full week."""

    def __init__(
        self,
        *,
        student_directory: StudentDirectory,
        event_provider: EventProvider,
        ects_analytics_provider: EctsAnalyticsProvider,
        risk_provider: RiskProvider,
        report_store: WeeklyReportStore,
        timezone: str,
        student_page_size: int = 100,
        execution_recorder: WorkflowExecutionRecorder | None = None,
    ) -> None:
        if student_page_size <= 0:
            raise ValueError("student_page_size must be positive")

        self._student_directory = student_directory
        self._event_provider = event_provider
        self._ects_analytics_provider = ects_analytics_provider
        self._risk_provider = risk_provider
        self._report_store = report_store
        self._timezone = _load_timezone(timezone)
        self._student_page_size = student_page_size
        self._execution_recorder = execution_recorder

    def run(
        self,
        *,
        now: datetime | None = None,
        trigger_type: TriggerType = "direct",
    ) -> WeeklyWorkflowResult:
        """Run directly or from the scheduler using a timezone-aware clock."""

        if self._execution_recorder is None:
            return self._run(now=now)

        execution_time = _as_local_datetime(now, self._timezone)
        period_start, period_end = _previous_completed_week(execution_time.date())
        return self._execution_recorder.run(
            workflow_name=WEEKLY_WORKFLOW_NAME,
            execution_key=f"weekly:{period_start.isoformat()}:{period_end.isoformat()}",
            trigger_type=trigger_type,
            operation=lambda: self._run(now=execution_time),
            outcome_for=_weekly_execution_outcome,
        )

    def _run(self, *, now: datetime | None = None) -> WeeklyWorkflowResult:
        """Execute the established weekly business workflow without logging policy."""

        started_at = _as_local_datetime(now, self._timezone)
        period_start, period_end = _previous_completed_week(started_at.date())
        execution_key = (
            f"weekly:{period_start.isoformat()}:{period_end.isoformat()}"
        )
        logger.info(
            "Weekly workflow started: execution_key=%s period_start=%s period_end=%s",
            execution_key,
            period_start.isoformat(),
            period_end.isoformat(),
        )

        academic_events = self._check_academic_events(period_start, period_end)
        directory, students = self._check_student_directory()
        progress = self._check_current_progress(students, directory)
        risks = self._check_current_risks(students, directory, period_end)
        sections = [academic_events, directory, progress, risks]
        # A supplied clock controls every timestamp in the result. Scheduled
        # executions use the real completion time.
        completed_at = datetime.now(self._timezone) if now is None else started_at
        result = WeeklyWorkflowResult(
            workflow_name=WEEKLY_WORKFLOW_NAME,
            execution_key=execution_key,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            status=_aggregate_status(sections),
            sections=sections,
            aggregate_metrics=_aggregate_metrics(sections),
            analytics=_build_weekly_analytics(
                period_start=period_start,
                period_end=period_end,
                timezone=self._timezone.key,
                sections=sections,
            ),
            persistence_status="not_attempted",
            warnings=_warnings_for(sections),
            errors=_errors_for(sections),
        )
        result = self._persist(
            result,
            period_start=period_start,
            period_end=period_end,
            started_at=started_at,
            completed_at=completed_at,
        )
        logger.info(
            "Weekly workflow finished: status=%s persistence_status=%s "
            "event_count=%s student_count=%s progress_count=%s risk_count=%s",
            result.status,
            result.persistence_status,
            academic_events.count,
            directory.count,
            progress.count,
            risks.count,
        )
        return result

    def _check_academic_events(
        self, period_start: date, period_end: date
    ) -> WeeklyReportSection:
        try:
            result = self._event_provider.get_upcoming_events(
                start_date=period_start.isoformat(),
                end_date=(period_end - timedelta(days=1)).isoformat(),
            )
        except Exception:
            logger.exception("Weekly workflow academic-event report failed")
            return WeeklyReportSection(
                name="academic_events",
                status="failed",
                count=None,
                reason_codes=["ACADEMIC_EVENTS_CHECK_FAILED"],
            )

        if not isinstance(result, dict) or result.get("success") is not True:
            return WeeklyReportSection(
                name="academic_events",
                status="unavailable",
                count=None,
                reason_codes=[_result_code(result, "ACADEMIC_EVENTS_UNAVAILABLE")],
            )
        events = result.get("events")
        if not isinstance(events, list):
            return WeeklyReportSection(
                name="academic_events",
                status="unavailable",
                count=None,
                reason_codes=["ACADEMIC_EVENTS_MALFORMED"],
            )
        return WeeklyReportSection(
            name="academic_events",
            status="completed",
            count=len(events),
            details={"events_found": len(events)},
        )

    def _check_student_directory(
        self,
    ) -> tuple[WeeklyReportSection, list[dict[str, Any]]]:
        try:
            students = self._list_students()
        except Exception:
            logger.exception("Weekly workflow student-directory report failed")
            return (
                WeeklyReportSection(
                    name="student_directory",
                    status="failed",
                    count=None,
                    reason_codes=["STUDENT_DIRECTORY_CHECK_FAILED"],
                ),
                [],
            )
        return (
            WeeklyReportSection(
                name="student_directory",
                status="completed",
                count=len(students),
                details={"students_discovered": len(students)},
            ),
            students,
        )

    def _check_current_progress(
        self,
        students: list[dict[str, Any]],
        directory: WeeklyReportSection,
    ) -> WeeklyReportSection:
        if directory.status != "completed":
            return WeeklyReportSection(
                name="current_progress",
                status="unavailable",
                count=None,
                reason_codes=["STUDENT_DIRECTORY_UNAVAILABLE"],
            )
        student_ids = _student_ids(students)
        malformed_count = len(students) - len(student_ids)
        if not student_ids:
            if malformed_count:
                return WeeklyReportSection(
                    name="current_progress",
                    status="failed",
                    count=None,
                    details={"malformed_student_records": malformed_count},
                    reason_codes=["STUDENT_RECORD_MALFORMED"],
                )
            return WeeklyReportSection(
                name="current_progress",
                status="completed",
                count=0,
                details={
                    "students_processed": 0,
                    "students_failed": 0,
                    "behind_count": 0,
                    "on_track_count": 0,
                    "ahead_count": 0,
                },
            )
        try:
            result = self._ects_analytics_provider.calculate_ects_for_cohort(
                student_ids
            )
        except Exception:
            logger.exception("Weekly workflow current-progress report failed")
            return WeeklyReportSection(
                name="current_progress",
                status="failed",
                count=None,
                reason_codes=["ECTS_ANALYTICS_CHECK_FAILED"],
            )
        if not isinstance(result, dict):
            return WeeklyReportSection(
                name="current_progress",
                status="unavailable",
                count=None,
                reason_codes=["ECTS_ANALYTICS_MALFORMED"],
            )

        processed = result.get("processed")
        failed = result.get("failed")
        summary = result.get("summary")
        if (
            not _is_nonnegative_int(processed)
            or not _is_nonnegative_int(failed)
            or not isinstance(summary, dict)
        ):
            return WeeklyReportSection(
                name="current_progress",
                status="unavailable",
                count=None,
                reason_codes=["ECTS_ANALYTICS_MALFORMED"],
            )
        details = {
            "students_processed": processed,
            "students_failed": failed + malformed_count,
        }
        for key in ("behind_count", "on_track_count", "ahead_count"):
            value = summary.get(key)
            if _is_nonnegative_int(value):
                details[key] = value
        for key in ("average_completed_ects", "average_progress_percentage"):
            value = summary.get(key)
            if _is_nonnegative_number(value):
                details[key] = value

        if processed == 0:
            status: SectionStatus = "failed" if failed or malformed_count else "unavailable"
            count: int | None = None
        elif failed or malformed_count:
            status = "partial"
            count = processed
        else:
            status = "completed"
            count = processed
        return WeeklyReportSection(
            name="current_progress",
            status=status,
            count=count,
            details=details,
            reason_codes=(
                ["STUDENT_RECORD_MALFORMED"] if malformed_count else []
            ),
        )

    def _check_current_risks(
        self,
        students: list[dict[str, Any]],
        directory: WeeklyReportSection,
        as_of_date: date,
    ) -> WeeklyReportSection:
        if directory.status != "completed":
            return WeeklyReportSection(
                name="current_academic_risks",
                status="unavailable",
                count=None,
                reason_codes=["STUDENT_DIRECTORY_UNAVAILABLE"],
            )
        if not students:
            return WeeklyReportSection(
                name="current_academic_risks",
                status="completed",
                count=0,
                details={
                    "students_assessed": 0,
                    "complete_assessments": 0,
                    "partial_assessments": 0,
                    "unavailable_assessments": 0,
                    "failed_assessments": 0,
                    "risk_levels_available": 0,
                    "low_risk_count": 0,
                    "medium_risk_count": 0,
                    "high_risk_count": 0,
                    "critical_risk_count": 0,
                    "partial_risk_count": 0,
                    "unavailable_risk_count": 0,
                    "tutor_attention_count": 0,
                },
            )

        assessed = complete = partial = unavailable = failed = 0
        risk_levels_available = 0
        risk_level_counts = _empty_risk_level_counts()
        reason_codes: list[str] = []
        for student in students:
            student_id = student.get("id") if isinstance(student, dict) else None
            if not _is_valid_student_id(student_id):
                failed += 1
                reason_codes.append("STUDENT_RECORD_MALFORMED")
                continue
            try:
                result = self._risk_provider.assess_student_risk(
                    student_id,
                    as_of_date=as_of_date,
                )
            except Exception:
                logger.exception("Weekly workflow academic-risk report failed")
                failed += 1
                reason_codes.append("ACADEMIC_RISK_CHECK_FAILED")
                continue
            if not isinstance(result, dict) or result.get("success") is not True:
                unavailable += 1
                reason_codes.append(
                    _result_code(result, "ACADEMIC_RISK_UNAVAILABLE")
                )
                continue
            assessment_status = result.get("assessment_status")
            if assessment_status not in {"COMPLETE", "PARTIAL"}:
                failed += 1
                reason_codes.append("ACADEMIC_RISK_MALFORMED")
                continue
            assessed += 1
            if assessment_status == "COMPLETE":
                risk_level = result.get("risk_level")
                if risk_level not in risk_level_counts:
                    assessed -= 1
                    failed += 1
                    reason_codes.append("ACADEMIC_RISK_MALFORMED")
                    continue
                complete += 1
                risk_levels_available += 1
                risk_level_counts[risk_level] += 1
            else:
                partial += 1

        details = {
            "students_assessed": assessed,
            "complete_assessments": complete,
            "partial_assessments": partial,
            "unavailable_assessments": unavailable,
            "failed_assessments": failed,
            "risk_levels_available": risk_levels_available,
            "low_risk_count": risk_level_counts["LOW"],
            "medium_risk_count": risk_level_counts["MEDIUM"],
            "high_risk_count": risk_level_counts["HIGH"],
            "critical_risk_count": risk_level_counts["CRITICAL"],
            "partial_risk_count": partial,
            # Failed, malformed, and explicitly unavailable canonical results
            # share this mutually exclusive report bucket. Their separate
            # source-quality counts remain above so a consumer can distinguish
            # degraded data from a valid PARTIAL assessment.
            "unavailable_risk_count": unavailable + failed,
            "tutor_attention_count": (
                risk_level_counts["MEDIUM"]
                + risk_level_counts["HIGH"]
                + risk_level_counts["CRITICAL"]
            ),
        }
        if assessed == len(students) and complete == assessed:
            status: SectionStatus = "completed"
        elif assessed:
            status = "partial"
        elif failed:
            status = "failed"
        else:
            status = "unavailable"
        if partial and risk_levels_available == 0:
            reason_codes.append("RISK_LEVELS_UNAVAILABLE_FOR_PARTIAL_ASSESSMENTS")
        return WeeklyReportSection(
            name="current_academic_risks",
            status=status,
            count=assessed if status in {"completed", "partial"} else None,
            details=details,
            reason_codes=_deduplicate(reason_codes),
        )

    def _list_students(self) -> list[dict[str, Any]]:
        students: list[dict[str, Any]] = []
        offset = 0
        expected_total: int | None = None
        while expected_total is None or offset < expected_total:
            page, total = self._student_directory.search_students(
                limit=self._student_page_size,
                offset=offset,
            )
            if not isinstance(page, list) or not _is_nonnegative_int(total):
                raise ValueError("Student directory returned an invalid page")
            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise ValueError("Student directory total changed during weekly workflow")
            if not page:
                if offset < expected_total:
                    raise ValueError("Student directory ended before its reported total")
                break
            students.extend(page)
            offset += len(page)
            if offset > expected_total:
                raise ValueError("Student directory exceeded its reported total")
        return students

    def _persist(
        self,
        result: WeeklyWorkflowResult,
        *,
        period_start: date,
        period_end: date,
        started_at: datetime,
        completed_at: datetime,
    ) -> WeeklyWorkflowResult:
        candidate = replace(result, persistence_status="saved")
        try:
            receipt = self._report_store.save_report(
                workflow_name=candidate.workflow_name,
                execution_key=candidate.execution_key,
                period_start=period_start,
                period_end=period_end,
                started_at=started_at,
                completed_at=completed_at,
                status=candidate.status,
                report_payload=candidate.to_dict(),
            )
        except Exception:
            logger.exception("Weekly workflow report persistence failed")
            return replace(
                result,
                status=_status_after_persistence_failure(result.status),
                persistence_status="failed",
                errors=[*result.errors, "report_persistence:WEEKLY_REPORT_STORE_FAILED"],
            )
        receipt_status = receipt.get("status") if isinstance(receipt, dict) else None
        report_id = receipt.get("report_id") if isinstance(receipt, dict) else None
        if receipt_status in {"saved", "already_stored"} and _is_valid_report_id(report_id):
            return replace(
                candidate,
                persistence_status=receipt_status,
                report_id=report_id,
            )
        return replace(
            result,
            status=_status_after_persistence_failure(result.status),
            persistence_status="failed",
            errors=[*result.errors, "report_persistence:WEEKLY_REPORT_STORE_MALFORMED"],
        )


def create_database_weekly_workflow(*, session: Any, timezone: str) -> WeeklyWorkflow:
    """Wire Issue #103 to existing services and its approved report store."""

    from app.repositories.workflow_execution_log_repository import (
        WorkflowExecutionLogRepository,
    )

    student_repository = StudentRepository(session)
    student_service = StudentService(student_repository)
    progress_service = ProgressService(ProgressRepository(session))
    study_right_service = StudyRightService(StudyRightRepository(session))
    event_service = EventService(EventRepository(session))
    delay_service = DelayDetectionService(progress_service)
    study_right_risk_service = StudyRightRiskService(
        study_right_service,
        student_service,
    )
    risk_service = AcademicRiskScoringService(
        delay_service,
        study_right_risk_service,
        _ReportScopedEventProvider(event_service),
        TutorMeetingRiskService(TutorMeetingRepository(session)),
    )
    return WeeklyWorkflow(
        student_directory=student_repository,
        event_provider=event_service,
        ects_analytics_provider=EctsAnalyticsService(progress_service),
        risk_provider=risk_service,
        report_store=WeeklyReportRepository(session),
        timezone=timezone,
        execution_recorder=WorkflowExecutionRecorder(
            WorkflowExecutionLogRepository(session)
        ),
    )


def run_scheduled_weekly_workflow() -> WeeklyWorkflowResult:
    """Run with a short-lived database session from the existing scheduler."""

    session = SessionLocal()
    try:
        workflow = create_database_weekly_workflow(
            session=session,
            timezone=settings.weekly_workflow_timezone,
        )
        return workflow.run(trigger_type="scheduler")
    finally:
        session.close()


async def register_weekly_workflow(
    scheduler: Scheduler,
    *,
    job: Callable[[], Any] | None = None,
    hour: int | None = None,
    minute: int | None = None,
    timezone: str | None = None,
) -> bool:
    """Register the one recurring Monday weekly-report job."""

    configured_timezone = timezone or settings.weekly_workflow_timezone
    trigger = DailyTimeTrigger(
        hour=settings.weekly_workflow_hour if hour is None else hour,
        minute=settings.weekly_workflow_minute if minute is None else minute,
        days_of_week={MONDAY_WEEKDAY},
        tz=_load_timezone(configured_timezone),
    )
    try:
        await scheduler.register_job(
            WEEKLY_WORKFLOW_JOB_ID,
            job or run_scheduled_weekly_workflow,
            trigger,
        )
    except DuplicateJobError:
        logger.info("Weekly workflow job is already registered")
        return False
    logger.info(
        "Weekly workflow job registered: job_id=%s weekday=%s time=%02d:%02d timezone=%s",
        WEEKLY_WORKFLOW_JOB_ID,
        MONDAY_WEEKDAY,
        trigger.hour,
        trigger.minute,
        configured_timezone,
    )
    return True


def _previous_completed_week(local_date: date) -> tuple[date, date]:
    current_monday = local_date - timedelta(days=local_date.weekday())
    return current_monday - timedelta(days=7), current_monday


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
        logger.warning("Weekly workflow timezone %s is unavailable; using UTC", value)
        return ZoneInfo("UTC")


def _aggregate_status(sections: list[WeeklyReportSection]) -> WorkflowStatus:
    statuses = {section.status for section in sections}
    if statuses == {"completed"}:
        return "completed"
    if statuses == {"unavailable"}:
        return "unavailable"
    if "completed" in statuses or "partial" in statuses:
        return "partial"
    if "failed" in statuses:
        return "failed"
    return "unavailable"


def _weekly_execution_outcome(result: WeeklyWorkflowResult):
    return workflow_outcome(
        status=result.status,
        requested_count=len(result.sections),
        processed_count=sum(
            section.status in {"completed", "partial", "failed"}
            for section in result.sections
        ),
        succeeded_count=sum(
            section.status == "completed" for section in result.sections
        ),
        failed_count=sum(section.status == "failed" for section in result.sections),
        skipped_count=0,
        warnings=result.warnings,
        errors=result.errors,
    )


def _aggregate_metrics(
    sections: list[WeeklyReportSection],
) -> dict[str, int | float]:
    metrics: dict[str, int | float] = {}
    for section in sections:
        if section.count is not None:
            metrics[f"{section.name}_count"] = section.count
        for key, value in section.details.items():
            metrics[f"{section.name}_{key}"] = value
    return metrics


def _build_weekly_analytics(
    *,
    period_start: date,
    period_end: date,
    timezone: str,
    sections: list[WeeklyReportSection],
) -> dict[str, Any]:
    """Build the Issue #98 report from already-produced section results.

    This is deliberately an aggregation-only layer.  Progress is calculated
    once by ``EctsAnalyticsService`` and every risk assessment is supplied by
    ``AcademicRiskScoringService``; no weekly-specific score or ECTS formula
    is introduced here.
    """

    by_name = {section.name: section for section in sections}
    directory = by_name["student_directory"]
    progress = by_name["current_progress"]
    risks = by_name["current_academic_risks"]

    progress_details = progress.details
    risk_details = risks.details
    risk_distribution = {
        level: risk_details.get(f"{level.lower()}_risk_count")
        for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    }
    risk_distribution.update({
        "PARTIAL": risk_details.get("partial_risk_count"),
        "UNAVAILABLE": risk_details.get("unavailable_risk_count"),
    })
    progress_distribution = {
        "BEHIND": progress_details.get("behind_count"),
        "ON_TRACK": progress_details.get("on_track_count"),
        "AHEAD": progress_details.get("ahead_count"),
    }

    return {
        "report_period": {
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
            "end_exclusive": True,
            "timezone": timezone,
        },
        "population": {
            "status": directory.status,
            "student_count": directory.count,
        },
        "progress_statistics": {
            "status": progress.status,
            "students_processed": progress_details.get("students_processed"),
            "students_unavailable": progress_details.get("students_failed"),
            "behind_count": progress_distribution["BEHIND"],
            "on_track_count": progress_distribution["ON_TRACK"],
            "ahead_count": progress_distribution["AHEAD"],
            "average_completed_ects": progress_details.get(
                "average_completed_ects"
            ),
            "average_progress_percentage": progress_details.get(
                "average_progress_percentage"
            ),
        },
        "risk_summary": {
            "status": risks.status,
            "student_population_count": directory.count,
            "students_assessed": risk_details.get("students_assessed"),
            "LOW": risk_distribution["LOW"],
            "MEDIUM": risk_distribution["MEDIUM"],
            "HIGH": risk_distribution["HIGH"],
            "CRITICAL": risk_distribution["CRITICAL"],
            "PARTIAL": risk_distribution["PARTIAL"],
            "UNAVAILABLE": risk_distribution["UNAVAILABLE"],
            "requires_tutor_attention": risk_details.get("tutor_attention_count"),
        },
        "important_findings": {
            "kind": "CURRENT_WEEKLY_INDICATORS",
            "historical_comparison_available": False,
            "progress_distribution": progress_distribution,
            "risk_distribution": risk_distribution,
        },
        "data_quality": {
            "overall_status": _aggregate_status(sections),
            "section_statuses": {
                section.name: section.status for section in sections
            },
            "risk_complete_assessments": risk_details.get(
                "complete_assessments"
            ),
            "risk_partial_assessments": risk_details.get(
                "partial_assessments"
            ),
            "risk_explicitly_unavailable_assessments": risk_details.get(
                "unavailable_assessments"
            ),
            "risk_failed_assessments": risk_details.get("failed_assessments"),
        },
    }


def _warnings_for(sections: list[WeeklyReportSection]) -> list[str]:
    warnings = [
        "Current-progress metrics are cumulative state, not ECTS completed during the reporting period.",
        "Tutor-specific briefing text and delivery remain outside Issue #103.",
        "Tutor meetings, historical risk events, and Academic Health Score are unavailable in current contracts.",
    ]
    if any(section.name == "current_academic_risks" and section.status == "partial" for section in sections):
        warnings.append(
            "Academic-risk assessments are partial when an authoritative indicator is unavailable."
        )
    return warnings


def _errors_for(sections: list[WeeklyReportSection]) -> list[str]:
    return [
        f"{section.name}:{code}"
        for section in sections
        if section.status == "failed"
        for code in section.reason_codes
    ]


def _status_after_persistence_failure(status: WorkflowStatus) -> WorkflowStatus:
    if status in {"failed", "unavailable"}:
        return "failed"
    return "partial"


def _student_ids(students: list[dict[str, Any]]) -> list[int]:
    return sorted(
        {
            student["id"]
            for student in students
            if isinstance(student, dict) and _is_valid_student_id(student.get("id"))
        }
    )


def _empty_risk_level_counts() -> dict[str, int]:
    return {level: 0 for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")}


def _result_code(result: Any, default: str) -> str:
    if isinstance(result, dict):
        code = result.get("error")
        if isinstance(code, str) and code:
            return code
    return default


def _is_valid_student_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_valid_report_id(value: Any) -> bool:
    return _is_valid_student_id(value)


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
