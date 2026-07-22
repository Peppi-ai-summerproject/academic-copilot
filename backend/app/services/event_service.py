from datetime import date, datetime
from typing import Any

from app.repositories.event_repository import EventRepository


class EventService:
    """Business logic for upcoming academic events."""

    def __init__(self, repository: EventRepository) -> None:
        self._repository = repository

    def get_upcoming_events(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        parsed_start_date = self._parse_date(
            start_date,
            default=date.today(),
        )

        if parsed_start_date is None:
            return {
                "success": False,
                "error": "INVALID_START_DATE",
                "message": "Start date must use YYYY-MM-DD format.",
            }

        parsed_end_date = self._parse_date(end_date)

        if end_date is not None and parsed_end_date is None:
            return {
                "success": False,
                "error": "INVALID_END_DATE",
                "message": "End date must use YYYY-MM-DD format.",
            }

        if (
            parsed_end_date is not None
            and parsed_end_date < parsed_start_date
        ):
            return {
                "success": False,
                "error": "INVALID_DATE_RANGE",
                "message": "End date must not be before start date.",
            }

        rows = self._repository.get_upcoming_events(
            start_date=parsed_start_date,
            end_date=parsed_end_date,
        )

        events = [
            {
                "id": int(row["id"]),
                "event_name": str(row["event_name"]),
                "event_type": str(row["event_type"]),
                "event_date": row["event_date"].isoformat(),
                "end_date": (
                    row["end_date"].isoformat()
                    if row["end_date"] is not None
                    else None
                ),
                "academic_year": str(row["academic_year"]),
                "semester": int(row["semester"]),
                "description": row["description"],
                "affects_all_students": bool(
                    row["affects_all_students"]
                ),
            }
            for row in rows
        ]

        return {
            "success": True,
            "filters": {
                "start_date": parsed_start_date.isoformat(),
                "end_date": (
                    parsed_end_date.isoformat()
                    if parsed_end_date is not None
                    else None
                ),
            },
            "event_count": len(events),
            "events": events,
        }

    @staticmethod
    def _parse_date(
        value: str | None,
        default: date | None = None,
    ) -> date | None:
        if value is None:
            return default

        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None