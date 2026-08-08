"""Tutor-focused Monday preparation workflow for Issue #101.

The workflow coordinates existing repository and analytics contracts. It never
calculates academic indicators, persists execution records, or sends Telegram
messages.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.database import SessionLocal
from app.repositories.event_repository import EventRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.repositories.tutor_repository import TutorRepository
from app.repositories.tutor_meeting_repository import TutorMeetingRepository
from app.services.academic_risk_scoring_service import AcademicRiskScoringService
from app.services.delay_detection_service import DelayDetectionService
from app.services.event_service import EventService
from app.services.progress_service import ProgressService
from app.services.scheduler import DailyTimeTrigger, DuplicateJobError, Scheduler
from app.services.student_service import StudentService
from app.services.study_right_risk_service import StudyRightRiskService
from app.services.study_right_service import StudyRightService
from app.services.tutor_meeting_risk_service import TutorMeetingRiskService


logger = logging.getLogger("academic-copilot.workflows.monday")

MONDAY_WORKFLOW_JOB_ID = "monday_workflow"
MONDAY_WEEKDAY = 0


class TutorDirectory(Protocol):
    def list_active_tutors(self) -> list[dict[str, Any]]: ...

    def list_students_for_tutor(self, tutor_id: int) -> list[dict[str, Any]]: ...


class ProgressProvider(Protocol):
    def get_progress(self, student_id: int) -> dict[str, Any]: ...


class RiskProvider(Protocol):
    def assess_student_risk(
        self, student_id: int, *, as_of_date: date
    ) -> dict[str, Any]: ...


class EventProvider(Protocol):
    def get_upcoming_events(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class MondayTutorBriefing:
    """Delivery-independent briefing with an unsent Telegram representation."""

    tutor_id: int
    tutor_name: str
    generated_at: str
    week_start: str
    week_end: str
    summary: dict[str, int]
    priority_students: list[dict[str, Any]] = field(default_factory=list)
    upcoming_items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    delivery: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MondayWorkflowResult:
    status: str
    generated_at: str
    week_start: str
    week_end: str
    execution_key: str
    briefings: list[MondayTutorBriefing] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "briefings": [briefing.to_dict() for briefing in self.briefings],
        }


class MondayWorkflow:
    """Prepare deterministic weekly tutor briefings from verified services."""

    def __init__(
        self,
        *,
        tutor_directory: TutorDirectory,
        progress_provider: ProgressProvider,
        risk_provider: RiskProvider,
        event_provider: EventProvider,
        timezone: str,
    ) -> None:
        self._tutor_directory = tutor_directory
        self._progress_provider = progress_provider
        self._risk_provider = risk_provider
        self._event_provider = event_provider
        self._timezone = _load_timezone(timezone)

    def run(self, *, now: datetime | None = None) -> MondayWorkflowResult:
        local_now = _as_local_datetime(now, self._timezone)
        week_start = local_now.date() - timedelta(days=local_now.weekday())
        week_end = week_start + timedelta(days=6)
        generated_at = local_now.isoformat()
        execution_key = f"monday:all_tutors:{week_start.isoformat()}"

        events, event_warnings = self._load_upcoming_events(week_start, week_end)
        try:
            tutors = self._tutor_directory.list_active_tutors()
        except SQLAlchemyError:
            logger.exception("Monday workflow could not discover tutors")
            return _failed_result(
                generated_at=generated_at,
                week_start=week_start,
                week_end=week_end,
                execution_key=execution_key,
                error="Tutor discovery failed because the database was unavailable.",
            )

        if not tutors:
            return MondayWorkflowResult(
                status="completed",
                generated_at=generated_at,
                week_start=week_start.isoformat(),
                week_end=week_end.isoformat(),
                execution_key=execution_key,
                warnings=[*event_warnings, "No active tutors were found."],
            )

        briefings: list[MondayTutorBriefing] = []
        workflow_warnings = list(event_warnings)
        any_partial = bool(event_warnings)
        assigned_students = 0
        successful_analyses = 0
        failed_analyses = 0

        for tutor in tutors:
            briefing, analysis_counts = self._build_tutor_briefing(
                tutor=tutor,
                events=events,
                generated_at=generated_at,
                week_start=week_start,
                week_end=week_end,
                inherited_warnings=event_warnings,
            )
            briefings.append(briefing)
            assigned_students += analysis_counts["assigned"]
            successful_analyses += analysis_counts["successful"]
            failed_analyses += analysis_counts["failed"]
            any_partial = any_partial or bool(briefing.warnings)

        if assigned_students and not successful_analyses and failed_analyses:
            return MondayWorkflowResult(
                status="failed",
                generated_at=generated_at,
                week_start=week_start.isoformat(),
                week_end=week_end.isoformat(),
                execution_key=execution_key,
                briefings=briefings,
                warnings=workflow_warnings,
                errors=["Academic analysis failed for every assigned student."],
            )

        return MondayWorkflowResult(
            status="partial" if any_partial else "completed",
            generated_at=generated_at,
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            execution_key=execution_key,
            briefings=briefings,
            warnings=workflow_warnings,
        )

    def _load_upcoming_events(
        self, week_start: date, week_end: date
    ) -> tuple[list[dict[str, Any]], list[str]]:
        try:
            result = self._event_provider.get_upcoming_events(
                start_date=week_start.isoformat(),
                end_date=week_end.isoformat(),
            )
        except SQLAlchemyError:
            logger.exception("Monday workflow could not retrieve upcoming events")
            return [], ["Upcoming academic events could not be retrieved."]

        if not result.get("success"):
            return [], ["Upcoming academic events could not be retrieved."]
        events = result.get("events")
        if not isinstance(events, list):
            return [], ["Upcoming academic events were unavailable."]
        return [event for event in events if isinstance(event, dict)], []

    def _build_tutor_briefing(
        self,
        *,
        tutor: dict[str, Any],
        events: list[dict[str, Any]],
        generated_at: str,
        week_start: date,
        week_end: date,
        inherited_warnings: list[str],
    ) -> tuple[MondayTutorBriefing, dict[str, int]]:
        tutor_id = int(tutor["id"])
        tutor_name = str(tutor.get("display_name") or f"Tutor {tutor_id}")
        warnings = list(inherited_warnings)
        counts = {"assigned": 0, "successful": 0, "failed": 0}
        try:
            students = self._tutor_directory.list_students_for_tutor(tutor_id)
        except SQLAlchemyError:
            logger.exception("Monday workflow could not retrieve tutor assignments: tutor_id=%s", tutor_id)
            students = []
            warnings.append("Assigned students could not be retrieved.")

        priority_students: list[dict[str, Any]] = []
        for student in students:
            counts["assigned"] += 1
            analysis = self._analyze_student(student, week_start)
            warnings.extend(analysis["warnings"])
            if analysis["successful"]:
                counts["successful"] += 1
            else:
                counts["failed"] += 1
                warnings.append(
                    f"Academic analysis was unavailable for student {analysis['student_id']}."
                )
            if analysis["requires_attention"]:
                priority_students.append(analysis)

        priority_students.sort(
            key=lambda item: (
                -int(item.get("priority_score") or 0),
                -int(item.get("delay_ects") or 0),
                str(item.get("student_name") or ""),
                int(item["student_id"]),
            )
        )

        delivery = _telegram_delivery(
            telegram_chat_id=tutor.get("telegram_chat_id"),
            tutor_name=tutor_name,
            week_start=week_start,
            week_end=week_end,
            assigned_count=counts["assigned"],
            priority_students=priority_students,
            events=events,
            warnings=warnings,
        )
        if delivery["delivery_status"] == "NO_DESTINATION":
            warnings.append("Tutor Telegram destination is unavailable; no message was sent.")

        briefing = MondayTutorBriefing(
            tutor_id=tutor_id,
            tutor_name=tutor_name,
            generated_at=generated_at,
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            summary={
                "total_students": counts["assigned"],
                "analysed_students": counts["successful"],
                "students_needing_attention": len(priority_students),
            },
            priority_students=priority_students,
            upcoming_items=events,
            warnings=_deduplicate(warnings),
            delivery=delivery,
        )
        return briefing, counts

    def _analyze_student(self, student: dict[str, Any], as_of_date: date) -> dict[str, Any]:
        student_id = int(student["id"])
        progress_result = self._call_progress(student_id)
        risk_result = self._call_risk(student_id, as_of_date)
        progress = progress_result.get("progress") if progress_result.get("success") else None
        risk = risk_result if risk_result.get("success") else None
        warnings: list[str] = []
        if not isinstance(progress, dict):
            warnings.append(f"Academic progress is unavailable for student {student_id}.")
        if not isinstance(risk, dict):
            warnings.append(f"Risk indicators are unavailable for student {student_id}.")
        priority_score = risk.get("raw_subtotal") if risk else None
        contributions = risk.get("indicator_contributions", []) if risk else []
        requires_attention = any(
            isinstance(contribution, dict)
            and int(contribution.get("assigned_points") or 0) > 0
            for contribution in contributions
        )
        return {
            "student_id": student_id,
            "student_name": str(student.get("name") or f"Student {student_id}"),
            "student_number": student.get("student_number"),
            "programme": student.get("programme"),
            "progress": progress,
            "risk": risk,
            "priority_score": priority_score,
            "delay_ects": (
                progress.get("remaining_to_expected_ects", 0) if isinstance(progress, dict) else None
            ),
            "requires_attention": requires_attention,
            "successful": bool(progress or risk),
            "warnings": warnings,
        }

    def _call_progress(self, student_id: int) -> dict[str, Any]:
        try:
            return self._progress_provider.get_progress(student_id)
        except SQLAlchemyError:
            logger.exception("Monday workflow progress lookup failed: student_id=%s", student_id)
            return {"success": False, "error": "PROGRESS_UNAVAILABLE"}

    def _call_risk(self, student_id: int, as_of_date: date) -> dict[str, Any]:
        try:
            return self._risk_provider.assess_student_risk(student_id, as_of_date=as_of_date)
        except SQLAlchemyError:
            logger.exception("Monday workflow risk lookup failed: student_id=%s", student_id)
            return {"success": False, "error": "RISK_UNAVAILABLE"}


def create_database_monday_workflow(*, session: Any, timezone: str) -> MondayWorkflow:
    """Wire the workflow to existing repositories and analytics services."""
    student_service = StudentService(StudentRepository(session))
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
        event_service,
        TutorMeetingRiskService(TutorMeetingRepository(session)),
    )
    return MondayWorkflow(
        tutor_directory=TutorRepository(session),
        progress_provider=progress_service,
        risk_provider=risk_service,
        event_provider=event_service,
        timezone=timezone,
    )


def run_scheduled_monday_workflow() -> MondayWorkflowResult:
    """Run from the scheduler with a short-lived database session."""
    session = SessionLocal()
    try:
        workflow = create_database_monday_workflow(
            session=session,
            timezone=settings.scheduler_timezone,
        )
        result = workflow.run()
        logger.info(
            "Monday workflow finished: status=%s week_start=%s briefing_count=%d",
            result.status,
            result.week_start,
            len(result.briefings),
        )
        return result
    finally:
        session.close()


async def register_monday_workflow(
    scheduler: Scheduler,
    *,
    job: Callable[[], Any] | None = None,
    hour: int | None = None,
    minute: int | None = None,
    timezone: str | None = None,
) -> bool:
    """Register the one recurring Monday job on the existing scheduler."""
    configured_timezone = timezone or scheduler.timezone
    trigger = DailyTimeTrigger(
        hour=settings.monday_workflow_hour if hour is None else hour,
        minute=settings.monday_workflow_minute if minute is None else minute,
        days_of_week={MONDAY_WEEKDAY},
        tz=_load_timezone(configured_timezone),
    )
    try:
        await scheduler.register_job(
            MONDAY_WORKFLOW_JOB_ID,
            job or run_scheduled_monday_workflow,
            trigger,
        )
    except DuplicateJobError:
        logger.info("Monday workflow job is already registered")
        return False

    logger.info(
        "Monday workflow job registered: job_id=%s weekday=%s time=%02d:%02d timezone=%s",
        MONDAY_WORKFLOW_JOB_ID,
        MONDAY_WEEKDAY,
        trigger.hour,
        trigger.minute,
        configured_timezone,
    )
    return True


def _telegram_delivery(
    *,
    telegram_chat_id: Any,
    tutor_name: str,
    week_start: date,
    week_end: date,
    assigned_count: int,
    priority_students: list[dict[str, Any]],
    events: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    destination_available = isinstance(telegram_chat_id, int) and not isinstance(
        telegram_chat_id, bool
    )
    return {
        "channel": "telegram",
        "delivery_status": "NOT_SENT" if destination_available else "NO_DESTINATION",
        "telegram_chat_id": telegram_chat_id if destination_available else None,
        "text": _render_telegram_text(
            tutor_name=tutor_name,
            week_start=week_start,
            week_end=week_end,
            assigned_count=assigned_count,
            priority_students=priority_students,
            events=events,
            warnings=warnings,
        ),
    }


def _render_telegram_text(
    *,
    tutor_name: str,
    week_start: date,
    week_end: date,
    assigned_count: int,
    priority_students: list[dict[str, Any]],
    events: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    lines = [
        f"Monday briefing for {tutor_name}",
        f"Week: {week_start.isoformat()} to {week_end.isoformat()}",
        f"Assigned students: {assigned_count}",
        f"Students needing attention: {len(priority_students)}",
    ]
    if priority_students:
        lines.extend(["", "Priority students"])
        for student in priority_students:
            progress = student.get("progress") or {}
            remaining = progress.get("remaining_to_expected_ects")
            detail = f"; {remaining} ECTS below expected" if remaining else ""
            lines.append(f"- {student['student_name']}{detail}")
    else:
        lines.extend(["", "No students need verified attention this week."])

    if events:
        lines.extend(["", "Upcoming academic items"])
        for event in events:
            name = str(event.get("event_name") or "Academic event")
            event_date = str(event.get("event_date") or "date unavailable")
            lines.append(f"- {event_date}: {name}")
    if warnings:
        lines.extend(["", "Availability notes"])
        lines.extend(f"- {warning}" for warning in _deduplicate(warnings))
    return "\n".join(lines)


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
        logger.warning("Monday workflow timezone %s is unavailable; using UTC", value)
        return ZoneInfo("UTC")


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _failed_result(
    *,
    generated_at: str,
    week_start: date,
    week_end: date,
    execution_key: str,
    error: str,
) -> MondayWorkflowResult:
    return MondayWorkflowResult(
        status="failed",
        generated_at=generated_at,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        execution_key=execution_key,
        errors=[error],
    )
