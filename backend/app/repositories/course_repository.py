"""Database access for the canonical course catalogue."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class CourseRepository:
    """Read searchable course definitions and teacher assignments."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, course_id: int) -> dict[str, Any] | None:
        row = self._session.execute(
            text(
                """
                SELECT id, course_code, course_name, credits,
                       programme_code, semester, is_active
                FROM courses WHERE id = :course_id
                """
            ),
            {"course_id": course_id},
        ).mappings().first()
        return dict(row) if row is not None else None

    def get_by_code(self, course_code: str) -> dict[str, Any] | None:
        row = self._session.execute(
            text(
                """
                SELECT id, course_code, course_name, credits,
                       programme_code, semester, is_active
                FROM courses
                WHERE LOWER(course_code) = LOWER(:course_code)
                """
            ),
            {"course_code": course_code.strip()},
        ).mappings().first()
        return dict(row) if row is not None else None

    def search(self, query: str | None = None) -> list[dict[str, Any]]:
        parameters: dict[str, Any] = {}
        where_clause = ""
        if query and query.strip():
            where_clause = "WHERE LOWER(course_code) LIKE :query OR LOWER(course_name) LIKE :query"
            parameters["query"] = f"%{query.strip().lower()}%"
        rows = self._session.execute(
            text(
                f"""
                SELECT id, course_code, course_name, credits,
                       programme_code, semester, is_active
                FROM courses {where_clause}
                ORDER BY course_code ASC, id ASC
                """
            ),
            parameters,
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_teachers(
        self,
        course_id: int,
        *,
        assignment_role: str | None = None,
    ) -> list[dict[str, Any]]:
        role_clause = ""
        parameters: dict[str, Any] = {"course_id": course_id}
        if assignment_role is not None:
            role_clause = "AND assignment.assignment_role = :assignment_role"
            parameters["assignment_role"] = assignment_role
        rows = self._session.execute(
            text(
                f"""
                SELECT tutor.id, tutor.display_name, tutor.email,
                       assignment.assignment_role
                FROM teacher_course_assignments AS assignment
                INNER JOIN tutors AS tutor ON tutor.id = assignment.tutor_id
                WHERE assignment.course_id = :course_id AND tutor.is_active = TRUE
                  {role_clause}
                ORDER BY assignment.assignment_role ASC,
                         tutor.display_name ASC, tutor.id ASC
                """
            ),
            parameters,
        ).mappings().all()
        return [dict(row) for row in rows]
