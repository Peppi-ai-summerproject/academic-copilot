"""Service contracts for authoritative teacher-course assignments."""

from typing import Any

from app.repositories.course_repository import CourseRepository
from app.repositories.tutor_repository import TutorRepository


def _invalid_id(value: Any) -> bool:
    return not isinstance(value, int) or isinstance(value, bool) or value <= 0


def _normalize_role(value: Any) -> tuple[str | None, dict[str, Any] | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, {
            "success": False,
            "error": "INVALID_ROLE_FILTER",
            "message": "role must be a non-empty string or null.",
        }
    return value.strip().upper(), None


class TeacherAssignmentService:
    """Resolve course/teacher relationships without fuzzy identity lookup."""

    def __init__(
        self,
        teachers: TutorRepository,
        courses: CourseRepository,
    ) -> None:
        self._teachers = teachers
        self._courses = courses

    def get_course_teachers(
        self,
        *,
        course_id: int | None = None,
        course_code: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        if (course_id is None) == (course_code is None):
            return {
                "success": False,
                "error": "INVALID_COURSE_IDENTIFIER",
                "message": "Provide exactly one of course_id or course_code.",
            }
        if course_id is not None:
            if _invalid_id(course_id):
                return {
                    "success": False,
                    "error": "INVALID_COURSE_ID",
                    "message": "course_id must be a positive integer.",
                }
            course = self._courses.get_by_id(course_id)
        else:
            normalized_code = course_code.strip() if isinstance(course_code, str) else ""
            if not normalized_code:
                return {
                    "success": False,
                    "error": "INVALID_COURSE_CODE",
                    "message": "course_code must be a non-empty string.",
                }
            course = self._courses.get_by_code(normalized_code)
        normalized_role, error = _normalize_role(role)
        if error:
            return error
        if course is None:
            return {
                "success": False,
                "error": "COURSE_NOT_FOUND",
                "message": "Course was not found.",
            }
        teachers = self._courses.list_teachers(
            course["id"],
            assignment_role=normalized_role,
        )
        return {
            "success": True,
            "course": course,
            "filter": {"role": normalized_role},
            "teacher_count": len(teachers),
            "teachers": teachers,
        }

    def get_teacher_courses(
        self,
        teacher_id: int,
        role: str | None = None,
    ) -> dict[str, Any]:
        if _invalid_id(teacher_id):
            return {
                "success": False,
                "error": "INVALID_TEACHER_ID",
                "message": "teacher_id must be a positive integer.",
            }
        normalized_role, error = _normalize_role(role)
        if error:
            return error
        teacher = self._teachers.get_by_id(teacher_id)
        if teacher is None:
            return {
                "success": False,
                "error": "TEACHER_NOT_FOUND",
                "message": "Teacher was not found.",
            }
        assignments = self._teachers.list_courses_for_teacher(
            teacher_id,
            assignment_role=normalized_role,
        )
        return {
            "success": True,
            "teacher": teacher,
            "filter": {"role": normalized_role},
            "assignment_count": len(assignments),
            "assignments": assignments,
        }
