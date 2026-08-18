"""MCP tools for authoritative teacher-course assignment lookup."""

from typing import Any

from app.db.database import SessionLocal
from app.repositories.course_repository import CourseRepository
from app.repositories.tutor_repository import TutorRepository
from app.services.teacher_assignment_service import TeacherAssignmentService


def _service(session: Any) -> TeacherAssignmentService:
    return TeacherAssignmentService(
        TutorRepository(session),
        CourseRepository(session),
    )


def get_course_teachers(
    course_id: int | None = None,
    course_code: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    """List active teachers assigned to one course, optionally by exact role."""
    session = SessionLocal()
    try:
        return _service(session).get_course_teachers(
            course_id=course_id,
            course_code=course_code,
            role=role,
        )
    except Exception:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Course teacher assignments could not be retrieved.",
        }
    finally:
        session.close()


def get_teacher_courses(
    teacher_id: int,
    role: str | None = None,
) -> dict[str, Any]:
    """List course assignments for one teacher, optionally by exact role."""
    session = SessionLocal()
    try:
        return _service(session).get_teacher_courses(teacher_id, role)
    except Exception:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Teacher course assignments could not be retrieved.",
        }
    finally:
        session.close()
