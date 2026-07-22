from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class ProgressRepository:
    """Database access layer for academic progress data."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_student_progress_data(
        self,
        student_id: int,
    ) -> dict[str, Any] | None:
        query = text(
            """
            SELECT
                s.id AS student_id,
                s.student_number,
                s.name,
                s.programme,
                COALESCE(SUM(cc.credits), 0) AS completed_ects,
                COALESCE(MAX(cc.semester), 1) AS current_semester
            FROM students s
            LEFT JOIN course_completions cc
                ON cc.student_id = s.id
            WHERE s.id = :student_id
            GROUP BY
                s.id,
                s.student_number,
                s.name,
                s.programme
            """
        )

        result = self._session.execute(
            query,
            {"student_id": student_id},
        ).mappings().first()

        return dict(result) if result is not None else None

    def get_expected_ects(
        self,
        programme: str,
        semester: int,
    ) -> int | None:
        query = text(
            """
            SELECT expected_ects
            FROM curriculum
            WHERE programme = :programme
              AND semester = :semester
            """
        )

        result = self._session.execute(
            query,
            {
                "programme": programme,
                "semester": semester,
            },
        ).scalar_one_or_none()

        return int(result) if result is not None else None