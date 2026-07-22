from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class CurriculumRepository:
    """Database access layer for curriculum information."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_programme(
        self,
        programme: str,
    ) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT
                programme,
                semester,
                expected_ects
            FROM curriculum
            WHERE programme = :programme
            ORDER BY semester
            """
        )

        rows = self._session.execute(
            query,
            {"programme": programme},
        ).mappings().all()

        return [dict(row) for row in rows]