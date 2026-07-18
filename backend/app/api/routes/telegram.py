import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, Request, status
from telegram import Update

from app.core.config import settings
from app.telegram.bot import create_bot


router = APIRouter()
logger = logging.getLogger(__name__)

telegram_application = create_bot()


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, str]:
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

    update = Update.de_json(
        payload,
        telegram_application.bot,
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
        await telegram_application.process_update(update)
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

    await telegram_application.initialize()
    await telegram_application.start()

    logger.info("Telegram application started in webhook mode")


async def shutdown_telegram_application() -> None:
    logger.info("Stopping Telegram application")

    await telegram_application.stop()
    await telegram_application.shutdown()

    logger.info("Telegram application stopped")