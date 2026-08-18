from collections.abc import Sequence
from typing import Any

from sqlalchemy import bindparam, text
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
                programme_code,
                email
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

    def get_by_student_number(self, student_number: str) -> dict[str, Any] | None:
        """Return a student by the exact, case-insensitive student number."""

        result = self._session.execute(
            text(
                """
                SELECT id, student_number, name, email, group_name, programme,
                       start_date, status, programme_code
                FROM students
                WHERE LOWER(student_number) = LOWER(:student_number)
                """
            ),
            {"student_number": student_number},
        ).mappings().first()
        return dict(result) if result is not None else None

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
                programme_code,
                email
            FROM students
            {where_clause}
            ORDER BY name ASC, student_number ASC, id ASC
            LIMIT :limit OFFSET :offset
            """
        )

        rows = self._session.execute(rows_sql, params).mappings().all()
        return [dict(row) for row in rows], total

    def list_active_student_ids(
        self,
        student_ids: Sequence[int] | None = None,
    ) -> list[int]:
        """Return only students with the canonical ``ACTIVE`` status.

        Optional IDs are intersected with the active-student population. This
        prevents a controlled subset from evaluating inactive, graduated,
        suspended, archived, or otherwise non-active students.
        """

        if student_ids is not None:
            normalized_ids = sorted(
                {
                    student_id
                    for student_id in student_ids
                    if isinstance(student_id, int)
                    and not isinstance(student_id, bool)
                    and student_id > 0
                }
            )
            if not normalized_ids:
                return []
            statement = text(
                """
                SELECT id
                FROM students
                WHERE status = :active_status
                  AND id IN :student_ids
                ORDER BY id ASC
                """
            ).bindparams(bindparam("student_ids", expanding=True))
            rows = self._session.execute(
                statement,
                {"active_status": "ACTIVE", "student_ids": normalized_ids},
            ).mappings().all()
        else:
            rows = self._session.execute(
                text(
                    """
                    SELECT id
                    FROM students
                    WHERE status = :active_status
                    ORDER BY id ASC
                    """
                ),
                {"active_status": "ACTIVE"},
            ).mappings().all()
        return [int(row["id"]) for row in rows]

