from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from telegram import Update

from app.agents.workflow import create_academic_agent_workflow
from app.api.routes import chat, telegram
from app.services.chat_service import ChatService
from app.services.session_service import SessionService
from app.telegram import backend_client as backend_client_module
from app.telegram import handlers


WEBHOOK_SECRET = "synthetic-e2e-webhook-secret"


class CapturingTelegramBot:
    def __init__(self) -> None:
        self.actions: list[dict] = []
        self.messages: list[dict] = []

    async def send_chat_action(self, **kwargs):
        self.actions.append(kwargs)
        return True

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return object()


class ProcessingTelegramApplication:
    def __init__(self, bot: CapturingTelegramBot) -> None:
        self.bot = bot
        self.processed_update_ids: list[int] = []

    async def process_update(self, update: Update) -> None:
        self.processed_update_ids.append(update.update_id)
        await handlers.handle_message(update, context=None)


def telegram_payload(
    *,
    update_id: int,
    user_id: int,
    chat_id: int,
    text: str,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "Synthetic Tutor",
                "username": f"synthetic_tutor_{user_id}",
            },
            "text": text,
        },
    }


@pytest.fixture
def journey(monkeypatch):
    sessions = SessionService()
    real_chat_service = ChatService(
        session_service=sessions,
        workflow=create_academic_agent_workflow(),
    )
    monkeypatch.setattr(chat, "chat_service", real_chat_service)

    backend_app = FastAPI()
    backend_app.include_router(chat.router, prefix="/api/v1/chat")

    real_async_client = httpx.AsyncClient

    def in_process_async_client(*args, **kwargs):
        return real_async_client(
            transport=httpx.ASGITransport(app=backend_app),
            base_url="http://backend.e2e.local",
            timeout=kwargs.get("timeout", 10.0),
        )

    monkeypatch.setattr(
        backend_client_module.httpx,
        "AsyncClient",
        in_process_async_client,
    )
    monkeypatch.setattr(
        backend_client_module.settings,
        "backend_base_url",
        "http://backend.e2e.local",
    )
    monkeypatch.setattr(
        backend_client_module.settings,
        "internal_service_key",
        "",
    )
    monkeypatch.setattr(handlers, "backend_client", backend_client_module.BackendClient())

    bot = CapturingTelegramBot()
    telegram_application = ProcessingTelegramApplication(bot)
    monkeypatch.setattr(telegram.settings, "telegram_webhook_enabled", True)
    monkeypatch.setattr(
        telegram.settings,
        "telegram_webhook_secret",
        WEBHOOK_SECRET,
    )
    monkeypatch.setattr(
        telegram,
        "get_telegram_application",
        lambda: telegram_application,
    )
    webhook_app = FastAPI()
    webhook_app.include_router(telegram.router, prefix="/api/v1/telegram")
    return TestClient(webhook_app), telegram_application, bot, sessions


@pytest.mark.e2e
def test_supported_telegram_message_crosses_real_application_and_returns_reply(
    journey,
) -> None:
    client, application, bot, sessions = journey

    response = client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
        json=telegram_payload(
            update_id=1001,
            user_id=7001,
            chat_id=8001,
            text="Hello Academic Copilot",
        ),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert application.processed_update_ids == [1001]
    assert len(bot.actions) == 1
    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 8001
    assert "Backend received your message successfully" in bot.messages[0]["text"]
    assert "Hello Academic Copilot" in bot.messages[0]["text"]
    session = sessions.get_session(7001)
    assert session is not None
    assert session.message_count == 1


@pytest.mark.e2e
def test_sequential_telegram_users_keep_session_and_response_data_isolated(
    journey,
) -> None:
    client, _, bot, sessions = journey

    for update_id, user_id, chat_id, text in (
        (2001, 7101, 8101, "Student Alpha synthetic request"),
        (2002, 7202, 8202, "Student Beta synthetic request"),
    ):
        response = client.post(
            "/api/v1/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
            json=telegram_payload(
                update_id=update_id,
                user_id=user_id,
                chat_id=chat_id,
                text=text,
            ),
        )
        assert response.status_code == 200

    assert [message["chat_id"] for message in bot.messages] == [8101, 8202]
    assert "Student Alpha" in bot.messages[0]["text"]
    assert "Student Beta" not in bot.messages[0]["text"]
    assert "Student Beta" in bot.messages[1]["text"]
    assert "Student Alpha" not in bot.messages[1]["text"]
    assert sessions.get_session(7101).telegram_chat_id == 8101
    assert sessions.get_session(7202).telegram_chat_id == 8202


@pytest.mark.e2e
def test_backend_transport_failure_returns_safe_tutor_facing_message(
    journey,
    monkeypatch,
) -> None:
    client, _, bot, _ = journey

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, json, headers):
            raise httpx.ConnectError(
                "synthetic backend unavailable",
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(
        backend_client_module.httpx,
        "AsyncClient",
        FailingAsyncClient,
    )
    monkeypatch.setattr(handlers, "backend_client", backend_client_module.BackendClient())

    response = client.post(
        "/api/v1/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
        json=telegram_payload(
            update_id=3001,
            user_id=7303,
            chat_id=8303,
            text="Synthetic request while backend is unavailable",
        ),
    )

    assert response.status_code == 200
    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 8303
    assert bot.messages[0]["text"] == (
        "I could not connect to the Academic Copilot backend.\n"
        "Please try again shortly."
    )
    assert "synthetic backend unavailable" not in bot.messages[0]["text"]
