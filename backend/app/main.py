from fastapi import FastAPI

from app.api.api_router import api_router
from app.core.config import settings
from app.core.logger import logger

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for the AI Academic Copilot project",
    debug=settings.debug,
)

logger.info(f"{settings.app_name} started successfully")

app.include_router(api_router)


@app.get("/")
def root():
    logger.info("Root endpoint called")

    return {
        "message": f"{settings.app_name} is running",
        "environment": settings.app_env,
    }