from fastapi import APIRouter

from app.core.logger import logger

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("/")
def health_check():
    logger.info("Health check endpoint called")
    return {"status": "healthy"}