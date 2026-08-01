from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.curriculum_repository import CurriculumRepository
from app.repositories.event_repository import EventRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.services.curriculum_service import CurriculumService
from app.services.event_service import EventService
from app.services.progress_service import ProgressService
from app.services.report_service import ReportService
from app.services.student_service import StudentService
from app.services.study_right_service import StudyRightService


def generate_report(
    student_id: int,
    report_type: str = "academic_summary",
) -> dict[str, Any]:
    """Generate a structured academic report for a student."""

    from app.db.database import SessionLocal

    database_session = SessionLocal()

    try:
        student_repository = StudentRepository(database_session)
        progress_repository = ProgressRepository(database_session)
        study_right_repository = StudyRightRepository(database_session)
        curriculum_repository = CurriculumRepository(database_session)
        event_repository = EventRepository(database_session)

        student_service = StudentService(student_repository)
        progress_service = ProgressService(progress_repository)
        study_right_service = StudyRightService(study_right_repository)
        curriculum_service = CurriculumService(curriculum_repository)
        event_service = EventService(event_repository)

        report_service = ReportService(
            student_service=student_service,
            progress_service=progress_service,
            study_right_service=study_right_service,
            curriculum_service=curriculum_service,
            event_service=event_service,
        )

        return report_service.generate_report(
            student_id,
            report_type=report_type,
        )

    except SQLAlchemyError:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Failed to generate the academic report.",
        }

    finally:
        database_session.close()
