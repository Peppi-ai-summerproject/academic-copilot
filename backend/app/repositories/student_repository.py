from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class StudentRepository:
    """Database access layer for student records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, student_id: int) -> dict[str, Any] | None:
        """Return a student by database ID."""

        query = text(
            """
            SELECT
                id,
                student_number,
                name,
                group_name,
                programme,
                start_date,
                status,
                programme_code
            FROM students
            WHERE id = :student_id
            """
        )

        result = self._session.execute(
            query,
            {"student_id": student_id},
        ).mappings().first()

        if result is None:
            return None

        return dict(result)

    def search_students(
        self,
        query: str | None = None,
        programme_code: str | None = None,
        group_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search students by name, student number, or structured filters.

        Args:
            query: Free-text search across name and student_number (case-insensitive).
            programme_code: Exact match on programme_code field.
            group_name: Exact match on group_name field.
            limit: Maximum number of records to return.
            offset: Number of records to skip for pagination.

        Returns:
            Tuple of (list of student dicts, total matching count).
        """
        # Build WHERE conditions
        conditions = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if query:
            conditions.append(
                "(LOWER(name) LIKE :name_pattern "
                "OR LOWER(student_number) LIKE :num_pattern)"
            )
            pattern = f"%{query.lower()}%"
            params["name_pattern"] = pattern
            params["num_pattern"] = pattern

        if programme_code:
            conditions.append("programme_code = :programme_code")
            params["programme_code"] = programme_code

        if group_name:
            conditions.append("group_name = :group_name")
            params["group_name"] = group_name

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        count_sql = text(f"SELECT COUNT(*) FROM students {where_clause}")
        total: int = self._session.execute(count_sql, params).scalar() or 0

        rows_sql = text(
            f"""
            SELECT
                id,
                student_number,
                name,
                group_name,
                programme,
                start_date,
                status,
                programme_code
            FROM students
            {where_clause}
            ORDER BY name ASC, student_number ASC, id ASC
            LIMIT :limit OFFSET :offset
            """
        )

        rows = self._session.execute(rows_sql, params).mappings().all()
        return [dict(row) for row in rows], total

