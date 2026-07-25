"""MCP tool for searching student records."""

from typing import Any

from app.db.database import SessionLocal
from app.repositories.student_repository import StudentRepository
from app.services.student_search_service import StudentSearchService


def search_students(
    query: str | None = None,
    programme_code: str | None = None,
    group_name: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Search student profiles using partial identity information
    and optional academic filters.

    Args:
        query: Free-text search string matched against student name
               and student number using case-insensitive partial matching.
               Leave empty to return all students (paginated).
        programme_code: Exact programme code filter (e.g. "DIN2024S").
        group_name: Exact group name filter (e.g. "TT21A").
        limit: Maximum number of results (1–100, default 20).
        offset: Number of records to skip for pagination (default 0).

    Returns:
        A structured response with pagination metadata and a list of
        matching student records, or an error response on failure.
    """
    database_session = SessionLocal()

    try:
        repository = StudentRepository(database_session)
        service = StudentSearchService(repository)

        return service.search_students(
            query=query,
            programme_code=programme_code,
            group_name=group_name,
            limit=limit,
            offset=offset,
        )
    except Exception:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Student search could not be completed.",
        }
    finally:
        database_session.close()
