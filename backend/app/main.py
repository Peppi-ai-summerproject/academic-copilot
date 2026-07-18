from fastapi import FastAPI

from app.api.api_router import api_router
from app.core.config import settings
from app.core.exception_handlers import (
    app_exception_handler,
    unhandled_exception_handler,
)
from app.core.exceptions import AppException
from app.core.logger import logger

from contextlib import asynccontextmanager

from app.api.routes.telegram import (
    initialize_telegram_application,
    shutdown_telegram_application,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.telegram_webhook_enabled:
        await initialize_telegram_application()

    yield

    if settings.telegram_webhook_enabled:
        await shutdown_telegram_application()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for the AI Academic Copilot project",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_exception_handler(
    AppException,
    app_exception_handler,
)

app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)

app.include_router(
    api_router,
    prefix="/api/v1",
)

logger.info("%s started successfully", settings.app_name)


@app.get("/")
def root():
    return {
        "message": f"{settings.app_name} is running",
        "environment": settings.app_env,
    }