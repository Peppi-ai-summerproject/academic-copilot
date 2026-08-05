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
    # Initialize Telegram application if enabled in settings
    if settings.telegram_webhook_enabled:
        await initialize_telegram_application()

    # Initialize scheduler if enabled. The scheduler is created and started
    # here to ensure it is bound to the FastAPI application lifecycle and not
    # started at import time.
    scheduler = None
    if settings.scheduler_enabled:
        from app.services.scheduler import Scheduler

        try:
            scheduler = Scheduler(timezone=settings.scheduler_timezone)
            await scheduler.start()
            from app.workflows.monday import register_monday_workflow

            await register_monday_workflow(scheduler)
            # keep a reference on the app so other parts of the code can access it
            app.state.scheduler = scheduler
        except Exception:
            # Log and re-raise to prevent partially initialized app
            from app.core.logger import logger as _logger

            _logger.exception("Failed to start scheduler")
            raise

    try:
        yield
    finally:
        # Shutdown scheduler if it was started
        if scheduler is not None:
            try:
                await scheduler.stop()
            except Exception:
                from app.core.logger import logger as _logger

                _logger.exception("Failed to stop scheduler")

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
