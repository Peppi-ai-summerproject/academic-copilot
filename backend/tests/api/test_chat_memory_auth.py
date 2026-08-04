from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.routes import chat as chat_route
from app.schemas.chat import ChatRequest, ChatResponse


class RecordingChatService:
    def __init__(self):
        self.trust: list[bool] = []

    async def process_message(self, request, *, trusted_telegram=False):
        self.trust.append(trusted_telegram)
        return ChatResponse(
            reply="ok", conversation_id=request.conversation_id or uuid4()
        )


def request(**changes):
    values = {"message": "hello", "telegram_user_id": 1, "telegram_chat_id": 2}
    values.update(changes)
    return ChatRequest(**values)


def test_optional_uuid_is_validated_and_returned(monkeypatch):
    recorder = RecordingChatService()
    monkeypatch.setattr(chat_route, "chat_service", recorder)
    conversation_id = uuid4()

    response = asyncio.run(chat_route.process_chat_message(request(conversation_id=conversation_id)))

    assert response.conversation_id == conversation_id
    with pytest.raises(ValidationError):
        request(conversation_id="not-a-uuid")


def test_missing_or_invalid_internal_secret_fails_closed(monkeypatch):
    recorder = RecordingChatService()
    monkeypatch.setattr(chat_route, "chat_service", recorder)
    monkeypatch.setattr(chat_route.settings, "internal_service_key", "expected")

    asyncio.run(chat_route.process_chat_message(request(), x_internal_service_key=None))
    asyncio.run(chat_route.process_chat_message(request(), x_internal_service_key="received-secret"))

    assert recorder.trust == [False, False]


def test_missing_configured_secret_fails_closed(monkeypatch):
    recorder = RecordingChatService()
    monkeypatch.setattr(chat_route, "chat_service", recorder)
    monkeypatch.setattr(chat_route.settings, "internal_service_key", "")

    asyncio.run(chat_route.process_chat_message(request(), x_internal_service_key="anything"))

    assert recorder.trust == [False]


def test_valid_internal_secret_enables_trusted_telegram_path(monkeypatch):
    recorder = RecordingChatService()
    monkeypatch.setattr(chat_route, "chat_service", recorder)
    monkeypatch.setattr(chat_route.settings, "internal_service_key", "expected")

    asyncio.run(chat_route.process_chat_message(request(), x_internal_service_key="expected"))

    assert recorder.trust == [True]
