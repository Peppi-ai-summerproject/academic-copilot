"""Service layer for student search functionality."""

from typing import Any

from app.repositories.student_repository import StudentRepository

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100
_MIN_LIMIT = 1


class StudentSearchService:
    """Business logic for searching student records.

    Handles input normalization, pagination validation,
    and response formatting. Does not access the database directly.
    """

    def __init__(self, repository: StudentRepository) -> None:
        self._repository = repository

    def search_students(
        self,
        query: str | None = None,
        programme_code: str | None = None,
        group_name: str | None = None,
        limit: int = _DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search for students by name, student number, or academic filters.

        Args:
            query: Free-text search string. Matched against name and
                   student_number using case-insensitive partial matching.
                   Leading/trailing whitespace is trimmed. Empty string
                   is treated as no free-text filter.
            programme_code: Exact programme code filter (e.g. "DIN2024S").
            group_name: Exact group name filter (e.g. "TT21A").
            limit: Maximum number of results to return (1–100, default 20).
            offset: Number of records to skip for pagination (>= 0).

        Returns:
            A JSON-serializable dict with success status, pagination metadata,
            and a list of matching student records.

        Empty search (no query, no filters) returns the first paginated page
        of all students ordered by name and student_number.
        """
        # Validate limit
        if not isinstance(limit, int) or limit < _MIN_LIMIT:
            return {
                "success": False,
                "error": "INVALID_SEARCH_PARAMETERS",
                "message": f"limit must be between {_MIN_LIMIT} and {_MAX_LIMIT}.",
            }
        if limit > _MAX_LIMIT:
            limit = _MAX_LIMIT

        # Validate offset
        if not isinstance(offset, int) or offset < 0:
            return {
                "success": False,
                "error": "INVALID_SEARCH_PARAMETERS",
                "message": "offset must be a non-negative integer.",
            }

        # Normalize query
        normalized_query: str | None = None
        if query is not None:
            stripped = query.strip()
            if stripped:
                normalized_query = stripped

        # Normalize structured filters
        normalized_programme_code: str | None = (
            programme_code.strip() if programme_code and programme_code.strip() else None
        )
        normalized_group_name: str | None = (
            group_name.strip() if group_name and group_name.strip() else None
        )

        students, total = self._repository.search_students(
            query=normalized_query,
            programme_code=normalized_programme_code,
            group_name=normalized_group_name,
            limit=limit,
            offset=offset,
        )

        returned = len(students)
        has_more = (offset + returned) < total

        return {
            "success": True,
            "query": {
                "text": normalized_query,
                "programme_code": normalized_programme_code,
                "group_name": normalized_group_name,
                "limit": limit,
                "offset": offset,
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned": returned,
                "total": total,
                "has_more": has_more,
            },
            "students": students,
        }
