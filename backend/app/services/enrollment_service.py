"""Service contracts for course rosters and student enrollments."""

from typing import Any, cast

from app.repositories.academic_record_repository import (
    AcademicRecordRepository,
    EnrollmentStatus,
)
from app.repositories.course_repository import CourseRepository
from app.repositories.student_repository import StudentRepository

_ENROLLMENT_STATUSES = {"ENROLLED", "IN_PROGRESS", "COMPLETED", "WITHDRAWN"}


def _invalid_id(value: Any) -> bool:
    return not isinstance(value, int) or isinstance(value, bool) or value <= 0


def _normalize_status(value: Any) -> tuple[EnrollmentStatus | None, dict[str, Any] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or value.strip().upper() not in _ENROLLMENT_STATUSES:
        return None, {
            "success": False,
            "error": "INVALID_ENROLLMENT_STATUS",
            "message": "enrollment_status must be ENROLLED, IN_PROGRESS, COMPLETED, or WITHDRAWN.",
        }
    return cast(EnrollmentStatus, value.strip().upper()), None


class EnrollmentService:
    def __init__(
        self,
        records: AcademicRecordRepository,
        students: StudentRepository,
        courses: CourseRepository,
    ) -> None:
        self._records = records
        self._students = students
        self._courses = courses

    def get_course_roster(
        self,
        course_id: int,
        enrollment_status: str | None = None,
    ) -> dict[str, Any]:
        if _invalid_id(course_id):
            return {"success": False, "error": "INVALID_COURSE_ID", "message": "course_id must be a positive integer."}
        status, error = _normalize_status(enrollment_status)
        if error:
            return error
        course = self._courses.get_by_id(course_id)
        if course is None:
            return {"success": False, "error": "COURSE_NOT_FOUND", "message": f"Course with ID {course_id} was not found."}
        students = self._records.list_students_for_course(course_id, enrollment_status=status)
        return {
            "success": True,
            "course": course,
            "filter": {"enrollment_status": status},
            "student_count": len(students),
            "students": students,
        }

    def get_student_enrollments(
        self,
        student_id: int,
        enrollment_status: str | None = None,
    ) -> dict[str, Any]:
        if _invalid_id(student_id):
            return {"success": False, "error": "INVALID_STUDENT_ID", "message": "student_id must be a positive integer."}
        status, error = _normalize_status(enrollment_status)
        if error:
            return error
        student = self._students.get_by_id(student_id)
        if student is None:
            return {"success": False, "error": "STUDENT_NOT_FOUND", "message": f"Student with ID {student_id} was not found."}
        courses = self._records.list_courses_for_student(student_id, enrollment_status=status)
        return {
            "success": True,
            "student": student,
            "filter": {"enrollment_status": status},
            "course_count": len(courses),
            "courses": courses,
        }

    def get_enrollment(self, student_id: int, course_id: int) -> dict[str, Any]:
        if _invalid_id(student_id):
            return {"success": False, "error": "INVALID_STUDENT_ID", "message": "student_id must be a positive integer."}
        if _invalid_id(course_id):
            return {"success": False, "error": "INVALID_COURSE_ID", "message": "course_id must be a positive integer."}
        if self._students.get_by_id(student_id) is None:
            return {"success": False, "error": "STUDENT_NOT_FOUND", "message": f"Student with ID {student_id} was not found."}
        if self._courses.get_by_id(course_id) is None:
            return {"success": False, "error": "COURSE_NOT_FOUND", "message": f"Course with ID {course_id} was not found."}
        enrollment = self._records.get_enrollment(student_id, course_id)
        if enrollment is None:
            return {"success": False, "error": "ENROLLMENT_NOT_FOUND", "message": "The student is not enrolled in this course."}
        return {"success": True, "enrollment": enrollment}
