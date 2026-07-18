import secrets

from fastapi import APIRouter, Header, HTTPException, Request, status
from telegram import Update

from app.core.config import settings
from app.telegram.bot import create_bot


router = APIRouter()

telegram_application = create_bot()


async def initialize_telegram_application() -> None:
    await telegram_application.initialize()
    await telegram_application.start()


async def shutdown_telegram_application() -> None:
    await telegram_application.stop()
    await telegram_application.shutdown()


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    if not secrets.compare_digest(
        x_telegram_bot_api_secret_token or "",
        settings.telegram_webhook_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Telegram webhook secret",
        )

    payload = await request.json()

    update = Update.de_json(
        payload,
        telegram_application.bot,
    )

    await telegram_application.process_update(update)

    return {"status": "ok"}