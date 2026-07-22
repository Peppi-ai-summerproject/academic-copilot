from typing import Any

from app.db.database import SessionLocal
from app.repositories.study_right_repository import StudyRightRepository
from app.services.study_right_service import StudyRightService


def get_study_right(student_id: int) -> dict[str, Any]:
    """Retrieve a student's study right information and status."""

    database_session = SessionLocal()

    try:
        repository = StudyRightRepository(database_session)
        service = StudyRightService(repository)

        return service.get_study_right(student_id)
    except Exception:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Study right information could not be retrieved.",
        }
    finally:
        database_session.close()