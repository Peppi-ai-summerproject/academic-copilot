"""MCP tools for authoritative course roster and enrollment lookup."""

from typing import Any

from app.db.database import SessionLocal
from app.repositories.academic_record_repository import AcademicRecordRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.student_repository import StudentRepository
from app.services.enrollment_service import EnrollmentService


def _service(session: Any) -> EnrollmentService:
    return EnrollmentService(
        AcademicRecordRepository(session),
        StudentRepository(session),
        CourseRepository(session),
    )


def get_course_roster(course_id: int, enrollment_status: str | None = None) -> dict[str, Any]:
    """Return a course roster, optionally filtered by enrollment status."""
    session = SessionLocal()
    try:
        return _service(session).get_course_roster(course_id, enrollment_status)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "The course roster could not be retrieved."}
    finally:
        session.close()


def get_student_enrollments(student_id: int, enrollment_status: str | None = None) -> dict[str, Any]:
    """Return a student's courses, optionally filtered by enrollment status."""
    session = SessionLocal()
    try:
        return _service(session).get_student_enrollments(student_id, enrollment_status)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "Student enrollments could not be retrieved."}
    finally:
        session.close()


def get_enrollment(student_id: int, course_id: int) -> dict[str, Any]:
    """Return one student-course enrollment using canonical numeric IDs."""
    session = SessionLocal()
    try:
        return _service(session).get_enrollment(student_id, course_id)
    except Exception:
        return {"success": False, "error": "DATABASE_ERROR", "message": "The enrollment could not be retrieved."}
    finally:
        session.close()
