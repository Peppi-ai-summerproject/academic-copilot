import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, Request, status
from telegram import Update
from telegram.ext import Application

from app.core.config import settings
from app.telegram.bot import create_bot


router = APIRouter()
logger = logging.getLogger(__name__)

telegram_application: Application | None = None


def get_telegram_application() -> Application:
    """Create the Telegram client only when the integration is used."""
    global telegram_application
    if telegram_application is None:
        telegram_application = create_bot()
    return telegram_application


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
    if not settings.telegram_webhook_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram webhook is disabled",
        )

    if not secrets.compare_digest(
        x_telegram_bot_api_secret_token or "",
        settings.telegram_webhook_secret,
    ):
        logger.warning("Rejected Telegram webhook request: invalid secret")

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Telegram webhook secret",
        )

    payload = await request.json()

    application = get_telegram_application()
    update = Update.de_json(
        payload,
        application.bot,
    )

    logger.info(
        "Telegram update received | "
        "update_id=%s | user_id=%s | chat_id=%s | update_type=%s",
        update.update_id,
        update.effective_user.id if update.effective_user else None,
        update.effective_chat.id if update.effective_chat else None,
        _get_update_type(update),
    )

    try:
        await application.process_update(update)
    except Exception:
        logger.exception(
            "Telegram update processing failed | update_id=%s",
            update.update_id,
        )
        raise

    return {"status": "ok"}


def _get_update_type(update: Update) -> str:
    if update.message:
        return "message"

    if update.callback_query:
        return "callback_query"

    if update.edited_message:
        return "edited_message"

    return "other"


async def initialize_telegram_application() -> None:
    logger.info("Initializing Telegram application")

    application = get_telegram_application()
    await application.initialize()
    await application.start()

    logger.info("Telegram application started in webhook mode")


async def shutdown_telegram_application() -> None:
    logger.info("Stopping Telegram application")

    if telegram_application is None:
        return

    await telegram_application.stop()
    await telegram_application.shutdown()

    logger.info("Telegram application stopped")
