from datetime import datetime

from pydantic import BaseModel


class UserSession(BaseModel):
    telegram_user_id: int
    telegram_chat_id: int
    username: str | None = None

    message_count: int = 0
    last_message: str | None = None
    current_context: str | None = None

    created_at: datetime
    updated_at: datetime