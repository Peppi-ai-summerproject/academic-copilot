from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class StudyRightRepository:
    """Database access layer for study right records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_student_id(self, student_id: int) -> dict[str, Any] | None:
        query = text(
            """
            SELECT
                id,
                student_id,
                start_date,
                end_date,
                status,
                extension_count
            FROM study_rights
            WHERE student_id = :student_id
            """
        )

        result = self._session.execute(
            query,
            {"student_id": student_id},
        ).mappings().first()

        return dict(result) if result is not None else None