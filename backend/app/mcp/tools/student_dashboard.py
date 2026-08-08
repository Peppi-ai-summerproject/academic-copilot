"""MCP tool for retrieving a complete student dashboard."""

from typing import Any
from functools import lru_cache

from app.db.database import SessionLocal
from app.repositories.student_repository import StudentRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.repositories.event_repository import EventRepository
from app.repositories.tutor_meeting_repository import TutorMeetingRepository
from app.services.academic_health_score_service import AcademicHealthScoreService
from app.services.academic_risk_scoring_service import AcademicRiskScoringService
from app.services.delay_detection_service import DelayDetectionService
from app.services.student_service import StudentService
from app.services.progress_service import ProgressService
from app.services.study_right_service import StudyRightService
from app.services.event_service import EventService
from app.services.study_right_risk_service import StudyRightRiskService
from app.services.tutor_meeting_risk_service import TutorMeetingRiskService
from app.services.student_dashboard_service import StudentDashboardService


def _memoize_request_evidence(
    student_service: StudentService,
    progress_service: ProgressService,
    study_right_service: StudyRightService,
    event_service: EventService,
) -> None:
    """Cache overlapping evidence reads for the lifetime of one MCP request."""
    student_service.get_student = lru_cache(maxsize=None)(student_service.get_student)
    progress_service.get_progress = lru_cache(maxsize=None)(progress_service.get_progress)
    study_right_service.get_study_right = lru_cache(maxsize=None)(
        study_right_service.get_study_right
    )
    event_service.get_upcoming_events = lru_cache(maxsize=None)(
        event_service.get_upcoming_events
    )


def get_student_dashboard(student_id: int) -> dict[str, Any]:
    """
    Return a complete student overview including profile, academic
    progress, study right status, academic health, risk information, and upcoming
    academic or tutor actions.

    Use this tool when a tutor teacher or AI agent needs a full picture
    of a student's academic situation in one call. Accepts the student's
    numeric database ID and returns all available sections. Optional
    sections degrade gracefully if data is unavailable.

    Args:
        student_id: The numeric database ID of the student.

    Returns:
        A structured dashboard response or an error dict on failure.
    """
    db = SessionLocal()

    try:
        student_service = StudentService(StudentRepository(db))
        progress_service = ProgressService(ProgressRepository(db))
        study_right_service = StudyRightService(StudyRightRepository(db))
        event_service = EventService(EventRepository(db))

        # One request may consume the same evidence for dashboard sections and
        # canonical risk. Memoize service results so repositories are read once.
        _memoize_request_evidence(
            student_service,
            progress_service,
            study_right_service,
            event_service,
        )
        risk_service = AcademicRiskScoringService(
            DelayDetectionService(progress_service),
            StudyRightRiskService(study_right_service, student_service),
            event_service,
            TutorMeetingRiskService(TutorMeetingRepository(db)),
        )

        dashboard_service = StudentDashboardService(
            student_service=student_service,
            progress_service=progress_service,
            study_right_service=study_right_service,
            event_service=event_service,
            academic_health_service=AcademicHealthScoreService(risk_service),
            academic_risk_service=risk_service,
        )

        return dashboard_service.get_student_dashboard(student_id)

    except Exception:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Unable to generate student dashboard.",
        }
    finally:
        db.close()
