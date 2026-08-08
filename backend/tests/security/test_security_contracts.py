from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.api.dependencies import get_student_dashboard_service
from app.api.routes import progress, telegram
from app.main import app
from app.telegram import backend_client as backend_client_module


FAKE_WEBHOOK_SECRET = "test-webhook-secret"
FAKE_INTERNAL_KEY = "test-internal-service-key"
SENSITIVE_MARKER = "test-sensitive-marker-must-not-leak"


@pytest.mark.parametrize("provided_secret", [None, "invalid-test-secret"])
def test_telegram_webhook_rejects_untrusted_requests_without_secret_leakage(
    monkeypatch,
    caplog,
    provided_secret,
) -> None:
    application = FastAPI()
    application.include_router(telegram.router)
    monkeypatch.setattr(telegram.settings, "telegram_webhook_enabled", True)
    monkeypatch.setattr(
        telegram.settings,
        "telegram_webhook_secret",
        FAKE_WEBHOOK_SECRET,
    )

    def unexpected_application_lookup():
        raise AssertionError("Telegram must not be initialized before authentication")

    monkeypatch.setattr(
        telegram,
        "get_telegram_application",
        unexpected_application_lookup,
    )
    headers = (
        {"X-Telegram-Bot-Api-Secret-Token": provided_secret}
        if provided_secret is not None
        else {}
    )

    with caplog.at_level(logging.WARNING, logger=telegram.__name__):
        response = TestClient(application).post(
            "/webhook",
            headers=headers,
            json={"update_id": 123},
        )

    assert response.status_code == 403
    combined_output = response.text + caplog.text
    assert FAKE_WEBHOOK_SECRET not in combined_output
    if provided_secret is not None:
        assert provided_secret not in combined_output


def test_public_root_does_not_serialize_configured_secrets(monkeypatch) -> None:
    monkeypatch.setattr(app.state, "security_test_marker", SENSITIVE_MARKER, raising=False)
    from app.core.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", SENSITIVE_MARKER)
    monkeypatch.setattr(settings, "telegram_webhook_secret", SENSITIVE_MARKER)
    monkeypatch.setattr(settings, "internal_service_key", SENSITIVE_MARKER)
    monkeypatch.setattr(settings, "gemini_api_key", SENSITIVE_MARKER)

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert SENSITIVE_MARKER not in response.text


def test_dashboard_exception_response_does_not_expose_internal_details() -> None:
    class FailingDashboardService:
        def get_student_dashboard(self, student_id, *, as_of_date=None):
            raise RuntimeError(SENSITIVE_MARKER)

    application = FastAPI()
    application.include_router(progress.router, prefix="/api/v1/students")
    application.dependency_overrides[get_student_dashboard_service] = (
        FailingDashboardService
    )

    response = TestClient(application).get(
        "/api/v1/students/1/progress-dashboard"
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Unable to retrieve the progress dashboard."
    }
    assert SENSITIVE_MARKER not in response.text


def test_backend_client_failure_does_not_log_or_return_internal_key(
    monkeypatch,
    caplog,
) -> None:
    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, json, headers):
            request = httpx.Request("POST", url)
            raise httpx.ConnectError("test connection failure", request=request)

    monkeypatch.setattr(
        backend_client_module.settings,
        "internal_service_key",
        FAKE_INTERNAL_KEY,
    )
    monkeypatch.setattr(
        backend_client_module.httpx,
        "AsyncClient",
        FailingAsyncClient,
    )
    client = backend_client_module.BackendClient()

    with caplog.at_level(logging.ERROR, logger=backend_client_module.__name__):
        with pytest.raises(
            backend_client_module.BackendClientError,
            match="Backend communication failed",
        ) as captured:
            import asyncio

            asyncio.run(
                client.send_message(
                    message="synthetic message",
                    telegram_user_id=101,
                    telegram_chat_id=202,
                    username="synthetic-user",
                )
            )

    assert FAKE_INTERNAL_KEY not in caplog.text
    assert FAKE_INTERNAL_KEY not in str(captured.value)
