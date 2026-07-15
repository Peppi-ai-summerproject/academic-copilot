from telegram import Update
from telegram.ext import ContextTypes

from app.telegram.backend_client import (
    BackendClientError,
    backend_client,
)
from app.telegram.logger import (
    log_incoming_message,
    log_outgoing_message,
    log_telegram_error,
)


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
        return

    log_incoming_message(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        message_text=message.text,
    )

    await message.reply_chat_action("typing")

    try:
        reply = await backend_client.send_message(
            message=message.text,
            telegram_user_id=user.id,
            telegram_chat_id=chat.id,
            username=user.username,
        )

    except BackendClientError as exc:
        log_telegram_error(
            error=exc,
            user_id=user.id,
            chat_id=chat.id,
        )

        error_message = (
            "I could not connect to the Academic Copilot backend.\n"
            "Please try again shortly."
        )

        await message.reply_text(error_message)
        return

    await message.reply_text(reply)

    log_outgoing_message(
        user_id=user.id,
        chat_id=chat.id,
        reply_text=reply,
    )


async def handle_error(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    user_id = None
    chat_id = None

    if isinstance(update, Update):
        user = update.effective_user
        chat = update.effective_chat

        user_id = user.id if user else None
        chat_id = chat.id if chat else None

    error = context.error

    if isinstance(error, Exception):
        log_telegram_error(
            error=error,
            user_id=user_id,
            chat_id=chat_id,
        )