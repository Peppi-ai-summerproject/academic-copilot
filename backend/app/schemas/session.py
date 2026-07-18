from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class UserSession(BaseModel):
    telegram_user_id: int
    telegram_chat_id: int
    username: str | None = None

    message_count: int = 0
    last_message: str | None = None
    current_context: str | None = None

    history: list[ConversationMessage] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime