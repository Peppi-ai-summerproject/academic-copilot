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

    def get_by_id(self, tutor_id: int) -> dict[str, Any] | None:
        row = self._session.execute(
            text(
                """
                SELECT id, display_name, email, is_active
                FROM tutors
                WHERE id = :tutor_id
                """
            ),
            {"tutor_id": tutor_id},
        ).mappings().first()
        return dict(row) if row is not None else None

    def search_by_name(self, query: str) -> list[dict[str, Any]]:
        rows = self._session.execute(
            text(
                """
                SELECT id, display_name, email, is_active
                FROM tutors
                WHERE LOWER(display_name) LIKE :name_pattern
                ORDER BY display_name ASC, id ASC
                """
            ),
            {"name_pattern": f"%{query.strip().lower()}%"},
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_courses_for_teacher(
        self,
        tutor_id: int,
        *,
        assignment_role: str | None = None,
    ) -> list[dict[str, Any]]:
        role_clause = ""
        parameters: dict[str, Any] = {"tutor_id": tutor_id}
        if assignment_role is not None:
            role_clause = "AND assignment.assignment_role = :assignment_role"
            parameters["assignment_role"] = assignment_role
        rows = self._session.execute(
            text(
                f"""
                SELECT
                    course.id,
                    course.course_code,
                    course.course_name,
                    course.credits,
                    course.programme_code,
                    course.semester,
                    course.is_active,
                    assignment.assignment_role
                FROM teacher_course_assignments AS assignment
                INNER JOIN courses AS course ON course.id = assignment.course_id
                WHERE assignment.tutor_id = :tutor_id
                  {role_clause}
                ORDER BY course.course_code ASC, course.id ASC,
                         assignment.assignment_role ASC
                """
            ),
            parameters,
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

    def list_active_tutor_recipients_for_student(
        self,
        student_id: int,
    ) -> list[dict[str, Any]]:
        """Return administrator-provisioned private delivery context.

        This is intentionally a narrow recipient-resolution query: the
        assignment join proves the academic scope, while ``is_active`` and the
        two stored Telegram identifiers are the approved administrative
        authorization boundary for Issue #107.  Registration, identity proof,
        preferences, and group-chat support are outside this repository.
        """

        rows = self._session.execute(
            text(
                """
                SELECT
                    tutor.id AS tutor_id,
                    tutor.telegram_user_id,
                    tutor.telegram_chat_id,
                    student.name AS student_display_name
                FROM tutor_student_assignments AS assignment
                INNER JOIN tutors AS tutor ON tutor.id = assignment.tutor_id
                INNER JOIN students AS student ON student.id = assignment.student_id
                WHERE assignment.student_id = :student_id
                  AND tutor.is_active = TRUE
                  AND tutor.telegram_user_id IS NOT NULL
                  AND tutor.telegram_chat_id IS NOT NULL
                ORDER BY tutor.id ASC
                """
            ),
            {"student_id": student_id},
        ).mappings().all()
        return [dict(row) for row in rows]
