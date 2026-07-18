from fastapi import APIRouter

from app.api.dependencies import DatabaseSessionDep, HealthServiceDep
from app.core.logger import logger

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("/")
def health_check(
    health_service: HealthServiceDep,
) -> dict[str, str]:
    logger.info("Health check endpoint called")
    return health_service.get_status()


@router.get("/database")
def database_health_check(
    database_session: DatabaseSessionDep,
    health_service: HealthServiceDep,
) -> dict[str, str]:
    logger.info("Database health check endpoint called")

    return health_service.get_database_status(
        database_session=database_session,
    )