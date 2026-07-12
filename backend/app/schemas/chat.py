from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    telegram_user_id: int
    telegram_chat_id: int
    username: str | None = None


class ChatResponse(BaseModel):
    reply: str