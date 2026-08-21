"""Database access for canonical student groups and their courses."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class StudentGroupRepository:
    """Read normalized cohorts without coupling them to course identity."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_code(self, group_code: str) -> dict[str, Any] | None:
        row = self._session.execute(
            text(
                """
                SELECT student_group.id, student_group.group_code,
                       student_group.group_name, student_group.programme_id,
                       programme.programme_code, programme.programme_name,
                       student_group.is_active
                FROM student_groups AS student_group
                INNER JOIN degree_programmes AS programme
                    ON programme.id = student_group.programme_id
                WHERE LOWER(student_group.group_code) = LOWER(:group_code)
                """
            ),
            {"group_code": group_code.strip()},
        ).mappings().first()
        return dict(row) if row is not None else None

    def get_by_id(self, group_id: int) -> dict[str, Any] | None:
        row = self._session.execute(
            text(
                """
                SELECT student_group.id, student_group.group_code,
                       student_group.group_name, student_group.programme_id,
                       programme.programme_code, programme.programme_name,
                       student_group.is_active
                FROM student_groups AS student_group
                INNER JOIN degree_programmes AS programme
                    ON programme.id = student_group.programme_id
                WHERE student_group.id = :group_id
                """
            ),
            {"group_id": group_id},
        ).mappings().first()
        return dict(row) if row is not None else None

    def search(self, query: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        where = ""
        if query:
            where = "WHERE LOWER(group_code) LIKE :query OR LOWER(group_name) LIKE :query"
            params["query"] = f"%{query.strip().lower()}%"
        rows = self._session.execute(
            text(
                f"""
                SELECT student_group.id, student_group.group_code,
                       student_group.group_name, student_group.programme_id,
                       programme.programme_code, programme.programme_name,
                       student_group.is_active
                FROM student_groups AS student_group
                INNER JOIN degree_programmes AS programme
                    ON programme.id = student_group.programme_id
                {where}
                ORDER BY student_group.group_code ASC, student_group.id ASC
                """
            ),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_students(self, group_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            text(
                """
                SELECT id, student_number, name, email, status
                FROM students
                WHERE group_id = :group_id
                ORDER BY name ASC, student_number ASC, id ASC
                """
            ),
            {"group_id": group_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_courses(self, group_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            text(
                """
                SELECT course.id, course.course_code, course.course_name,
                       course.credits, course.semester, course.is_active
                FROM student_group_courses AS association
                INNER JOIN courses AS course ON course.id = association.course_id
                WHERE association.group_id = :group_id
                ORDER BY course.course_code ASC, course.id ASC
                """
            ),
            {"group_id": group_id},
        ).mappings().all()
        return [dict(row) for row in rows]
