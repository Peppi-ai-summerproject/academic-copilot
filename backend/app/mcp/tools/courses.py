"""MCP tools for authoritative course catalogue discovery."""

from typing import Any

from app.db.database import SessionLocal
from app.repositories.course_repository import CourseRepository
from app.services.course_service import CourseService


def get_course(course_id: int | None = None, course_code: str | None = None) -> dict[str, Any]:
    """Find one course by exactly one unique identifier."""
    session = SessionLocal()
    try:
        return CourseService(CourseRepository(session)).get_course(course_id=course_id, course_code=course_code)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Course information could not be retrieved."}
    finally:
        session.close()


def search_courses(query: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """Search course names/codes case-insensitively, or list the catalogue."""
    session = SessionLocal()
    try:
        return CourseService(CourseRepository(session)).search_courses(query, limit, offset)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Course search could not be completed."}
    finally:
        session.close()
