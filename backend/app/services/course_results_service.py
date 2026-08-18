"""Deterministic course-result views and enrollment-based analytics."""
from typing import Any
from app.repositories.academic_record_repository import AcademicRecordRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.student_repository import StudentRepository

VALID_STATUSES = {"PASSED", "FAILED", "IN_PROGRESS", "NO_RESULT"}

class CourseResultsService:
    def __init__(self, records: AcademicRecordRepository, courses: CourseRepository, students: StudentRepository) -> None:
        self._records, self._courses, self._students = records, courses, students

    def course_results(self, course_code: str, status: str | None = None) -> dict[str, Any]:
        course = self._course(course_code)
        if not course.get("success"): return course
        valid = self._status(status)
        if valid is not None: return valid
        rows = self._records.list_course_result_view(course["course"]["id"])
        if status: rows = [row for row in rows if row["result_status"] == status.upper()]
        return {"success": True, "course": course["course"], "count": len(rows), "results": rows}

    def student_results(self, student_id: int, status: str | None = None) -> dict[str, Any]:
        if not isinstance(student_id, int) or isinstance(student_id, bool) or student_id <= 0:
            return {"success": False, "error": "INVALID_STUDENT_ID", "message": "student_id must be a positive integer."}
        student = self._students.get_by_id(student_id)
        if student is None: return {"success": False, "error": "STUDENT_NOT_FOUND", "message": "Student was not found."}
        valid = self._status(status)
        if valid is not None: return valid
        rows = self._records.list_student_result_view(student_id)
        if status: rows = [row for row in rows if row["result_status"] == status.upper()]
        return {"success": True, "student": student, "count": len(rows), "results": rows}

    def analytics(self, course_code: str) -> dict[str, Any]:
        result = self.course_results(course_code)
        if not result.get("success"): return result
        counts = {status.lower() + "_count": 0 for status in VALID_STATUSES}
        for row in result["results"]: counts[row["result_status"].lower() + "_count"] += 1
        enrolled = result["count"]; completed = counts["passed_count"] + counts["failed_count"]
        rate = lambda value: value / enrolled if enrolled else 0.0
        return {"success": True, "course": result["course"], "analytics": {"enrolled_count": enrolled, **counts, "completed_count": completed, "pass_rate": rate(counts["passed_count"]), "failure_rate": rate(counts["failed_count"]), "completion_rate": rate(completed)}}

    def _course(self, code: str) -> dict[str, Any]:
        if not isinstance(code, str) or not code.strip(): return {"success": False, "error": "INVALID_COURSE_CODE", "message": "course_code must be a non-empty string."}
        course = self._courses.get_by_code(code)
        return {"success": True, "course": course} if course else {"success": False, "error": "COURSE_NOT_FOUND", "message": "Course was not found."}
    def _status(self, status: str | None) -> dict[str, Any] | None:
        if status is not None and (not isinstance(status, str) or status.upper() not in VALID_STATUSES): return {"success": False, "error": "INVALID_RESULT_STATUS", "message": "status must be PASSED, FAILED, IN_PROGRESS, or NO_RESULT."}
        return None
