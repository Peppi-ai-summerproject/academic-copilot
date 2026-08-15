from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.core.config import settings
from app.telegram.commands import (
    events_command,
    help_command,
    progress_command,
    risk_command,
    start_command,
    status_command,
    student_command,
    unknown_command,
)
from app.telegram.handlers import (
    handle_error,
    handle_message,
)


def create_bot() -> Application:
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start_command)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("status", status_command)
    )

    application.add_handler(CommandHandler("student", student_command))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("risk", risk_command))
    application.add_handler(CommandHandler("events", events_command))

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.COMMAND,
            unknown_command,
        )
    )

    application.add_error_handler(handle_error)

    return application
