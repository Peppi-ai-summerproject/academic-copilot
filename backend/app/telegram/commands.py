import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.telegram.backend_client import BackendClientError, backend_client
from app.telegram.logger import (
    log_incoming_message,
    log_outgoing_message,
    log_telegram_error,
)

logger = logging.getLogger(__name__)


ACADEMIC_COMMAND_MESSAGES = {
    # There is no student agent; the reporting intent is the authoritative
    # student-overview capability and receives dependencies in ChatService.
    "student": "Give me an academic summary of this student.",
    "progress": "How is this student progressing?",
    "risk": "Is this student at academic risk?",
    "events": "Show upcoming academic events and deadlines.",
}


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
        "/student <student_id> - Get an academic student summary\n"
        "/progress <student_id> - View academic progress\n"
        "/risk <student_id> - Assess academic risk\n"
        "/events <student_id> - View upcoming academic events"
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


async def student_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _academic_command(update, context, "student")


async def progress_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _academic_command(update, context, "progress")


async def risk_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _academic_command(update, context, "risk")


async def events_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await _academic_command(update, context, "events")


async def _academic_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command: str,
) -> None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or message.text is None or user is None or chat is None:
        return

    log_incoming_message(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        message_text=message.text,
    )

    student_id, validation_error = _parse_student_id(context.args, command)
    if validation_error is not None:
        await message.reply_text(validation_error)
        log_outgoing_message(
            user_id=user.id,
            chat_id=chat.id,
            reply_text=validation_error,
        )
        return

    await message.reply_chat_action("typing")

    try:
        reply = await backend_client.send_message(
            message=ACADEMIC_COMMAND_MESSAGES[command],
            telegram_user_id=user.id,
            telegram_chat_id=chat.id,
            username=user.username,
            student_id=student_id,
        )
    except BackendClientError as exc:
        log_telegram_error(error=exc, user_id=user.id, chat_id=chat.id)
        await message.reply_text(
            "I could not connect to the Academic Copilot backend.\n"
            "Please try again shortly."
        )
        return

    await message.reply_text(reply)
    log_outgoing_message(user_id=user.id, chat_id=chat.id, reply_text=reply)


def _parse_student_id(
    args: list[str],
    command: str,
) -> tuple[int | None, str | None]:
    usage = f"/{command} 123"
    if not args:
        return None, f"Please provide a student ID, for example: {usage}"
    if len(args) != 1 or not args[0].isascii() or not args[0].isdigit():
        return None, f"Please provide one valid positive student ID, for example: {usage}"
    student_id = int(args[0])
    if student_id < 1:
        return None, f"Please provide one valid positive student ID, for example: {usage}"
    return student_id, None


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
