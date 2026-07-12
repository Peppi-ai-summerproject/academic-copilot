import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.telegram.backend_client import (
    BackendClientError,
    backend_client,
)

logger = logging.getLogger(__name__)


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if message is None or message.text is None:
        return

    if user is None or chat is None:
        logger.warning(
            "Telegram update has no user or chat information."
        )
        return

    logger.info(
        "Telegram message received: user_id=%s chat_id=%s",
        user.id,
        chat.id,
    )

    await message.reply_chat_action("typing")

    try:
        reply = await backend_client.send_message(
            message=message.text,
            telegram_user_id=user.id,
            telegram_chat_id=chat.id,
            username=user.username,
        )

    except BackendClientError:
        await message.reply_text(
            "I could not connect to the Academic Copilot backend.\n"
            "Please try again shortly."
        )
        return

    await message.reply_text(reply)