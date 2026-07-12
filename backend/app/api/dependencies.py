from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.services.health_service import HealthService


def get_db_session() -> Generator[Session, None, None]:
    database_session = SessionLocal()

    try:
        yield database_session
    finally:
        database_session.close()


DatabaseSessionDep = Annotated[
    Session,
    Depends(get_db_session),
]


def get_health_service() -> HealthService:
    return HealthService()


HealthServiceDep = Annotated[
    HealthService,
    Depends(get_health_service),
]