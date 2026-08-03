from pydantic import BaseModel, Field

from app.agents.types import AgentRoute


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    telegram_user_id: int
    telegram_chat_id: int
    username: str | None = None
    student_id: int | None = Field(default=None, ge=1)
    selected_agents: list[AgentRoute] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
