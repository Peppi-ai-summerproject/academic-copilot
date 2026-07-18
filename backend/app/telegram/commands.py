import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    user = update.effective_user

    if update.message is None:
        return

    logger.info(
        "User started the bot: telegram_user_id=%s username=%s",
        user.id if user else None,
        user.username if user else None,
    )

    await update.message.reply_text(
        "Welcome to Peppi AI Academic Copilot!\n\n"
        "I help tutor teachers access academic information, "
        "student progress, upcoming events, and risk insights.\n\n"
        "Use /help to see the available commands."
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "Available commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show available commands\n"
        "/status - Check whether the bot is running\n"
        "/student - Get student information\n"
        "/progress - View academic progress\n"
        "/risk - View students who may be at risk\n"
        "/events - View upcoming tutoring events\n\n"
        "Some academic commands are placeholders and will be "
        "connected to the backend and AI agents later."
    )


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "Peppi AI Academic Copilot is running."
    )


async def placeholder_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    command = update.message.text.split()[0]

    await update.message.reply_text(
        f"The {command} feature is not connected yet.\n"
        "It will be available after backend and MCP integration."
    )


async def unknown_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "Unknown command.\n"
        "Use /help to see the available commands."
    )