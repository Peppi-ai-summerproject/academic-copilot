"""Service contracts for teacher directory lookup and search."""

from typing import Any

from app.repositories.tutor_repository import TutorRepository
from app.services.course_service import _valid_page


class TeacherService:
    def __init__(self, repository: TutorRepository) -> None:
        self._repository = repository

    def get_teacher(self, teacher_id: int) -> dict[str, Any]:
        if not isinstance(teacher_id, int) or isinstance(teacher_id, bool) or teacher_id <= 0:
            return {"success": False, "error": "INVALID_TEACHER_ID", "message": "teacher_id must be a positive integer."}
        teacher = self._repository.get_by_id(teacher_id)
        if teacher is None:
            return {"success": False, "error": "TEACHER_NOT_FOUND", "message": "Teacher was not found."}
        return {"success": True, "teacher": teacher}

    def search_teachers(self, query: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        invalid = _valid_page(limit, offset)
        if invalid:
            return invalid
        if query is not None and not isinstance(query, str):
            return {"success": False, "error": "INVALID_SEARCH_QUERY", "message": "query must be a string or null."}
        normalized = query.strip() if isinstance(query, str) and query.strip() else None
        limit = min(limit, 100)
        candidates = self._repository.search_by_name(normalized or "")
        total = len(candidates)
        teachers = candidates[offset : offset + limit]
        return {"success": True, "query": {"text": normalized, "limit": limit, "offset": offset}, "pagination": {"limit": limit, "offset": offset, "returned": len(teachers), "total": total, "has_more": offset + len(teachers) < total}, "teachers": teachers}
