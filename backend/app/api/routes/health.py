from fastapi import APIRouter

from app.api.dependencies import HealthServiceDep
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