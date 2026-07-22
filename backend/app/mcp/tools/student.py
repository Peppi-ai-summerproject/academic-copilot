from typing import Any

from app.db.database import SessionLocal
from app.repositories.student_repository import StudentRepository
from app.services.student_service import StudentService


def get_student(student_id: int) -> dict[str, Any]:
    """
    Retrieve a student profile from the simulated Peppi database.

    Args:
        student_id: The numeric database ID of the student.

    Returns:
        A structured response containing either the student profile
        or an error describing why the student could not be returned.
    """

    database_session = SessionLocal()

    try:
        repository = StudentRepository(database_session)
        service = StudentService(repository)

        return service.get_student(student_id)
    except Exception:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Student information could not be retrieved.",
        }
    finally:
        database_session.close()