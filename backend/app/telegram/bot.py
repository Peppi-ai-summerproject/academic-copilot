from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.core.settings import settings
from app.telegram.commands import (
    help_command,
    placeholder_command,
    start_command,
    status_command,
    unknown_command,
)
from app.telegram.handlers import handle_message


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

    application.add_handler(
        CommandHandler(
            ["student", "progress", "risk", "events"],
            placeholder_command,
        )
    )

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

    return application