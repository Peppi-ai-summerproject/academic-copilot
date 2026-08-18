"""Database access for the canonical course catalogue."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class CourseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, course_id: int) -> dict[str, Any] | None:
        return self._get_one("id = :value", course_id)

    def get_by_code(self, course_code: str) -> dict[str, Any] | None:
        return self._get_one("LOWER(course_code) = LOWER(:value)", course_code)

    def _get_one(self, condition: str, value: int | str) -> dict[str, Any] | None:
        row = self._session.execute(
            text(
                f"""
                SELECT id, course_code, course_name, credits, programme, semester
                FROM courses WHERE {condition}
                """
            ),
            {"value": value},
        ).mappings().first()
        return dict(row) if row is not None else None

    def search_courses(self, query: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        where = ""
        if query:
            where = "WHERE LOWER(course_name) LIKE :pattern OR LOWER(course_code) LIKE :pattern"
            params["pattern"] = f"%{query.lower()}%"
        total = self._session.execute(text(f"SELECT COUNT(*) FROM courses {where}"), params).scalar() or 0
        rows = self._session.execute(
            text(
                f"""
                SELECT id, course_code, course_name, credits, programme, semester
                FROM courses {where}
                ORDER BY course_name ASC, course_code ASC, id ASC
                LIMIT :limit OFFSET :offset
                """
            ), params,
        ).mappings().all()
        return [dict(row) for row in rows], int(total)
