from fastapi import APIRouter
from app.core.exceptions import ResourceNotFoundException
from app.core.logger import logger

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("/")
def health_check():
    logger.info("Health check endpoint called")

    return {"status": "healthy"}


@router.get("/test-error")
def test_error():
    raise ResourceNotFoundException(
        resource="Student",
        resource_id=1001,
    )