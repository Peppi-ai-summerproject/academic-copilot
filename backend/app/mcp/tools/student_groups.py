"""MCP tools for canonical student groups."""

from typing import Any

from app.db.database import SessionLocal
from app.repositories.student_group_repository import StudentGroupRepository
from app.services.student_group_service import StudentGroupService


def _service(session) -> StudentGroupService:
    return StudentGroupService(StudentGroupRepository(session))


def search_student_groups(query: str | None = None) -> dict[str, Any]:
    session = SessionLocal()
    try:
        return _service(session).search_groups(query)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Student-group search failed."}
    finally:
        session.close()


def get_student_group(group_id: int) -> dict[str, Any]:
    session = SessionLocal()
    try:
        return _service(session).get_group(group_id)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Student group could not be retrieved."}
    finally:
        session.close()


def get_student_group_students(group_id: int) -> dict[str, Any]:
    session = SessionLocal()
    try:
        return _service(session).get_students(group_id)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Group students could not be retrieved."}
    finally:
        session.close()


def get_student_group_courses(group_id: int) -> dict[str, Any]:
    session = SessionLocal()
    try:
        return _service(session).get_courses(group_id)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Group courses could not be retrieved."}
    finally:
        session.close()
