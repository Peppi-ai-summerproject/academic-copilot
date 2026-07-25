from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.repositories.event_repository import EventRepository
from app.services.event_service import EventService


def get_upcoming_events(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Retrieve upcoming academic and tutoring events.

    Dates must use YYYY-MM-DD format.
    """

    db = SessionLocal()

    try:
        repository = EventRepository(db)
        service = EventService(repository)

        return service.get_upcoming_events(
            start_date=start_date,
            end_date=end_date,
        )

    except SQLAlchemyError:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Failed to retrieve upcoming events.",
        }

    finally:
        db.close()