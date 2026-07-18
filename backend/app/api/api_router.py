from fastapi import APIRouter

from app.api.routes import chat, health, sessions, telegram

api_router = APIRouter()

api_router.include_router(
    health.router,
    prefix="/health",
    tags=["Health"],
)

api_router.include_router(
    chat.router,
    prefix="/chat",
    tags=["Chat"],
)

api_router.include_router(
    sessions.router,
    prefix="/sessions",
    tags=["Sessions"],
)

api_router.include_router(
    telegram.router,
    prefix="/telegram",
    tags=["Telegram"],
)