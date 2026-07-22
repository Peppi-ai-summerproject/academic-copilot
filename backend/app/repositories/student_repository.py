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