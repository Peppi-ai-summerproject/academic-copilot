"""Database access for tutor-facing teacher directory records."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class TeacherRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, teacher_id: int) -> dict[str, Any] | None:
        row = self._session.execute(
            text("SELECT id, name, email, role FROM teachers WHERE id = :teacher_id"),
            {"teacher_id": teacher_id},
        ).mappings().first()
        return dict(row) if row is not None else None

    def search_teachers(self, query: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        where = ""
        if query:
            where = "WHERE LOWER(name) LIKE :pattern"
            params["pattern"] = f"%{query.lower()}%"
        total = self._session.execute(text(f"SELECT COUNT(*) FROM teachers {where}"), params).scalar() or 0
        rows = self._session.execute(
            text(
                f"""
                SELECT id, name, email, role FROM teachers {where}
                ORDER BY name ASC, id ASC LIMIT :limit OFFSET :offset
                """
            ), params,
        ).mappings().all()
        return [dict(row) for row in rows], int(total)
