"""Database access for tutor teachers and their current student assignments."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class TutorRepository:
    """Read tutor delivery context and student assignments for workflows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active_tutors(self) -> list[dict[str, Any]]:
        rows = self._session.execute(
            text(
                """
                SELECT id, display_name, telegram_user_id, telegram_chat_id
                FROM tutors
                WHERE is_active = TRUE
                ORDER BY display_name ASC, id ASC
                """
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_students_for_tutor(self, tutor_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            text(
                """
                SELECT
                    s.id,
                    s.student_number,
                    s.name,
                    s.programme,
                    s.group_name
                FROM tutor_student_assignments AS assignment
                INNER JOIN students AS s ON s.id = assignment.student_id
                WHERE assignment.tutor_id = :tutor_id
                ORDER BY s.name ASC, s.student_number ASC, s.id ASC
                """
            ),
            {"tutor_id": tutor_id},
        ).mappings().all()
        return [dict(row) for row in rows]
