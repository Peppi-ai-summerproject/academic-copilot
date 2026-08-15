from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
import httpx

from app.agents.registry import AgentRegistry
from app.agents.state import AgentState
from app.agents.types import WorkflowStatus
from app.api.routes import chat
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.session_service import SessionService
from app.telegram import backend_client as backend_client_module
from app.telegram import handlers


FINAL_RESPONSE = "Authoritative final academic response"


class FinalResponseWorkflow:
    async def run(self, state: AgentState) -> AgentState:
        state.workflow_status = WorkflowStatus.COMPLETED
        state.final_response = FINAL_RESPONSE
        return state


def test_chat_api_final_response_reaches_telegram_text_unchanged(monkeypatch) -> None:
    registry = AgentRegistry()
    registry.register("calendar", object)  # type: ignore[arg-type]
    sessions = SessionService()
    service = ChatService(
        session_service=sessions,
        workflow=FinalResponseWorkflow(),
        registry=registry,
    )
    monkeypatch.setattr(chat, "chat_service", service)

    app = FastAPI()
    app.include_router(chat.router, prefix="/api/v1/chat")
    real_async_client = httpx.AsyncClient

    def in_process_client(*args, **kwargs):
        return real_async_client(
            transport=httpx.ASGITransport(app=app),
            base_url="http://backend.test",
            timeout=kwargs.get("timeout", 10.0),
        )

    monkeypatch.setattr(backend_client_module.httpx, "AsyncClient", in_process_client)
    monkeypatch.setattr(backend_client_module.settings, "backend_base_url", "http://backend.test")
    monkeypatch.setattr(backend_client_module.settings, "internal_service_key", "")
    monkeypatch.setattr(
        handlers,
        "backend_client",
        backend_client_module.BackendClient(),
    )

    request = ChatRequest(
        message="Show upcoming academic events and deadlines.",
        telegram_user_id=101,
        telegram_chat_id=202,
    )
    direct_response = asyncio.run(service.process_message(request))

    message = SimpleNamespace(
        text=request.message,
        reply_text=AsyncMock(),
        reply_chat_action=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=101, username="tutor"),
        effective_chat=SimpleNamespace(id=202),
    )
    asyncio.run(handlers.handle_message(update, context=None))

    assert direct_response.reply == FINAL_RESPONSE
    message.reply_text.assert_awaited_once_with(FINAL_RESPONSE)
    session = sessions.get_session(101)
    assert session is not None
    assert session.message_count == 2
    assert session.history[-1].content == FINAL_RESPONSE
