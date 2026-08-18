"""Service contracts for course lookup and deterministic catalogue search."""

from typing import Any

from app.repositories.course_repository import CourseRepository

_MAX_LIMIT = 100


def _valid_page(limit: int, offset: int) -> dict[str, Any] | None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        return {"success": False, "error": "INVALID_SEARCH_PARAMETERS", "message": "limit must be positive and offset must be non-negative integers."}
    return None


class CourseService:
    def __init__(self, repository: CourseRepository) -> None:
        self._repository = repository

    def get_course(self, *, course_id: int | None = None, course_code: str | None = None) -> dict[str, Any]:
        if (course_id is None) == (course_code is None):
            return {"success": False, "error": "INVALID_COURSE_IDENTIFIER", "message": "Provide exactly one of course_id or course_code."}
        if course_id is not None:
            if not isinstance(course_id, int) or isinstance(course_id, bool) or course_id <= 0:
                return {"success": False, "error": "INVALID_COURSE_ID", "message": "course_id must be a positive integer."}
            course = self._repository.get_by_id(course_id)
        else:
            normalized = course_code.strip() if isinstance(course_code, str) else ""
            if not normalized:
                return {"success": False, "error": "INVALID_COURSE_CODE", "message": "course_code must be a non-empty string."}
            course = self._repository.get_by_code(normalized)
        if course is None:
            return {"success": False, "error": "COURSE_NOT_FOUND", "message": "Course was not found."}
        return {"success": True, "course": course}

    def search_courses(self, query: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        invalid = _valid_page(limit, offset)
        if invalid:
            return invalid
        if query is not None and not isinstance(query, str):
            return {"success": False, "error": "INVALID_SEARCH_QUERY", "message": "query must be a string or null."}
        normalized = query.strip() if isinstance(query, str) and query.strip() else None
        limit = min(limit, _MAX_LIMIT)
        courses, total = self._repository.search_courses(normalized, limit, offset)
        return {"success": True, "query": {"text": normalized, "limit": limit, "offset": offset}, "pagination": {"limit": limit, "offset": offset, "returned": len(courses), "total": total, "has_more": offset + len(courses) < total}, "courses": courses}
