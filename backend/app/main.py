from fastapi import FastAPI

from app.api.api_router import api_router
from app.core.config import settings
from app.core.exception_handlers import (
    app_exception_handler,
    unhandled_exception_handler,
)
from app.core.exceptions import AppException
from app.core.logger import logger

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for the AI Academic Copilot project",
    debug=settings.debug,
)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(api_router)

logger.info("%s started successfully", settings.app_name)


@app.get("/")
def root():
    return {
        "message": f"{settings.app_name} is running",
        "environment": settings.app_env,
    }