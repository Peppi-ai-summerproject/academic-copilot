import logging


telegram_logger = logging.getLogger("telegram")


def log_incoming_message(
    *,
    user_id: int,
    chat_id: int,
    username: str | None,
    message_text: str,
) -> None:
    telegram_logger.info(
        "Telegram message received | "
        "user_id=%s | chat_id=%s | username=%s | message=%r",
        user_id,
        chat_id,
        username,
        message_text,
    )


def log_outgoing_message(
    *,
    user_id: int,
    chat_id: int,
    reply_text: str,
) -> None:
    telegram_logger.info(
        "Telegram response sent | "
        "user_id=%s | chat_id=%s | reply=%r",
        user_id,
        chat_id,
        reply_text,
    )


def log_telegram_error(
    *,
    error: Exception,
    user_id: int | None = None,
    chat_id: int | None = None,
) -> None:
    telegram_logger.exception(
        "Telegram error | user_id=%s | chat_id=%s | error=%s",
        user_id,
        chat_id,
        error,
    )