from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.telegram import backend_client as module


def test_backend_client_sends_internal_header_and_ignores_extra_response_field(monkeypatch):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "reply": "Tutor response",
        "conversation_id": "83eb2d80-54ca-4ea8-b673-a85283cf0c06",
    }
    client = AsyncMock()
    client.post.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(module.httpx, "AsyncClient", MagicMock(return_value=context))
    monkeypatch.setattr(module.settings, "internal_service_key", "test-only-key")

    reply = asyncio.run(module.BackendClient().send_message(
        message="hello", telegram_user_id=1, telegram_chat_id=2, username="tutor"
    ))

    assert reply == "Tutor response"
    assert client.post.call_args.kwargs["headers"] == {
        "X-Internal-Service-Key": "test-only-key"
    }


def test_backend_client_omits_internal_header_when_key_is_unconfigured(monkeypatch):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"reply": "Tutor response"}
    client = AsyncMock()
    client.post.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(module.httpx, "AsyncClient", MagicMock(return_value=context))
    monkeypatch.setattr(module.settings, "internal_service_key", "")

    asyncio.run(module.BackendClient().send_message(
        message="hello", telegram_user_id=1, telegram_chat_id=2, username=None
    ))

    assert client.post.call_args.kwargs["headers"] == {}
