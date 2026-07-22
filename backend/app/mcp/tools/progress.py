from typing import Any

from app.db.database import SessionLocal
from app.repositories.progress_repository import ProgressRepository
from app.services.progress_service import ProgressService


def get_progress(student_id: int) -> dict[str, Any]:
    """Calculate and return a student's academic progress."""

    database_session = SessionLocal()

    try:
        repository = ProgressRepository(database_session)
        service = ProgressService(repository)

        return service.get_progress(student_id)
    except Exception:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Academic progress could not be retrieved.",
        }
    finally:
        database_session.close()