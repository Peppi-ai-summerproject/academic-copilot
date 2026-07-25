from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.repositories.curriculum_repository import CurriculumRepository
from app.services.curriculum_service import CurriculumService


def get_curriculum(programme: str) -> dict[str, Any]:
    """
    Retrieve curriculum information for a programme.
    """

    db = SessionLocal()

    try:
        repository = CurriculumRepository(db)
        service = CurriculumService(repository)

        return service.get_curriculum(programme)

    except SQLAlchemyError:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Failed to retrieve curriculum information.",
        }

    finally:
        db.close()