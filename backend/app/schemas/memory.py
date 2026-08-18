from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    interaction_status: Literal["completed", "partial"]
    created_at: datetime


class ConversationMemorySnapshot(BaseModel):
    conversation_id: UUID
    student_id: int | None = None
    messages: list[MemoryMessage] = Field(default_factory=list, max_length=20)
    resolved_entities: list[dict] = Field(default_factory=list)
