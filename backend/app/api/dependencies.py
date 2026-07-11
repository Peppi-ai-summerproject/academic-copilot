from typing import Annotated

from fastapi import Depends

from app.services.health_service import HealthService


def get_health_service() -> HealthService:
    return HealthService()


HealthServiceDep = Annotated[
    HealthService,
    Depends(get_health_service),
]