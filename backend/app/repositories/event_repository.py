from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class EventRepository:
    """Database access layer for academic and tutoring events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_upcoming_events(
        self,
        start_date: date,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                id,
                event_name,
                event_type,
                event_date,
                end_date,
                academic_year,
                semester,
                description,
                affects_all_students
            FROM academic_events
            WHERE event_date >= :start_date
        """

        parameters: dict[str, Any] = {
            "start_date": start_date,
        }

        if end_date is not None:
            query += " AND event_date <= :end_date"
            parameters["end_date"] = end_date

        query += " ORDER BY event_date ASC, id ASC"

        rows = (
            self._session.execute(
                text(query),
                parameters,
            )
            .mappings()
            .all()
        )

        return [dict(row) for row in rows]