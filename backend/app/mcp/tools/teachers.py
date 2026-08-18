"""MCP tools for the tutor-facing teacher directory."""

from typing import Any

from app.db.database import SessionLocal
from app.repositories.tutor_repository import TutorRepository
from app.services.teacher_service import TeacherService


def get_teacher(teacher_id: int) -> dict[str, Any]:
    """Retrieve a teacher directory record by numeric ID."""
    session = SessionLocal()
    try:
        return TeacherService(TutorRepository(session)).get_teacher(teacher_id)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Teacher information could not be retrieved."}
    finally:
        session.close()


def search_teachers(query: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Search teacher names case-insensitively, or list the directory."""
    session = SessionLocal()
    try:
        return TeacherService(TutorRepository(session)).search_teachers(query, limit, offset)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Teacher search could not be completed."}
    finally:
        session.close()
