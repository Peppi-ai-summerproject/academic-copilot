"""MCP tool for retrieving a complete student dashboard."""

from typing import Any

from app.db.database import SessionLocal
from app.repositories.student_repository import StudentRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.repositories.event_repository import EventRepository
from app.services.student_service import StudentService
from app.services.progress_service import ProgressService
from app.services.study_right_service import StudyRightService
from app.services.event_service import EventService
from app.services.student_dashboard_service import StudentDashboardService


def get_student_dashboard(student_id: int) -> dict[str, Any]:
    """
    Return a complete student overview including profile, academic
    progress, study right status, risk information, and upcoming
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

        dashboard_service = StudentDashboardService(
            student_service=student_service,
            progress_service=progress_service,
            study_right_service=study_right_service,
            event_service=event_service,
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
