"""Deterministic Issue #119 tests for important backend integration boundaries."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agents.progress_analysis_agent import ProgressAnalysisAgent
from app.api.dependencies import get_db_session
from app.api.routes import health, telegram


def _sqlite_engine():
    """Create an isolated SQLAlchemy connection for one API test."""

    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_database_health_route_uses_real_dependency_service_and_sqlalchemy_session():
    """FastAPI route -> dependency injection -> HealthService -> SQLAlchemy."""

    engine = _sqlite_engine()
    application = FastAPI()
    application.include_router(health.router)

    def database_session_override():
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_db_session] = database_session_override

    try:
        response = TestClient(application).get("/health/database")
    finally:
        engine.dispose()

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}


def test_telegram_webhook_parses_update_and_invokes_application_without_network(
    monkeypatch,
):
    """HTTP webhook -> Telegram Update parsing -> application dispatch."""

    class FakeApplication:
        def __init__(self) -> None:
            self.bot = object()
            self.processed_updates = []

        async def process_update(self, update) -> None:
            self.processed_updates.append(update)

    application = FastAPI()
    application.include_router(telegram.router)
    fake_telegram = FakeApplication()
    monkeypatch.setattr(telegram.settings, "telegram_webhook_enabled", True)
    monkeypatch.setattr(telegram.settings, "telegram_webhook_secret", "test-secret")
    monkeypatch.setattr(
        telegram,
        "get_telegram_application",
        lambda: fake_telegram,
    )

    response = TestClient(application).post(
        "/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={
            "update_id": 123,
            "message": {
                "message_id": 5,
                "date": 0,
                "chat": {"id": 902, "type": "private"},
                "from": {"id": 901, "is_bot": False, "first_name": "Tutor"},
                "text": "show progress",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(fake_telegram.processed_updates) == 1
    update = fake_telegram.processed_updates[0]
    assert update.update_id == 123
    assert update.effective_user.id == 901
    assert update.effective_chat.id == 902
    assert update.effective_message.text == "show progress"


def test_telegram_webhook_rejects_an_invalid_secret_before_application_dispatch(
    monkeypatch,
):
    """The external-update boundary rejects unauthenticated requests safely."""

    application = FastAPI()
    application.include_router(telegram.router)
    monkeypatch.setattr(telegram.settings, "telegram_webhook_enabled", True)
    monkeypatch.setattr(telegram.settings, "telegram_webhook_secret", "test-secret")

    def unexpected_application_lookup():
        raise AssertionError("Telegram application must not be selected")

    monkeypatch.setattr(
        telegram,
        "get_telegram_application",
        unexpected_application_lookup,
    )

    response = TestClient(application).post(
        "/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        json={"update_id": 123},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid Telegram webhook secret"}


class _MappingResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _AcademicToolSession:
    """Database boundary fake with real MCP tools, repositories, and services."""

    def __init__(self) -> None:
        self.closed = False
        self.queries: list[str] = []

    def execute(self, statement, _parameters):
        query = str(statement)
        self.queries.append(query)
        if "FROM students s" in query:
            return _MappingResult(
                {
                    "student_id": 42,
                    "student_number": "S042",
                    "name": "Aino Example",
                    "programme": "Business IT",
                    "completed_ects": 60,
                    "current_semester": 3,
                }
            )
        if "FROM curriculum" in query:
            return _ScalarResult(90)
        if "FROM students" in query:
            return _MappingResult(
                {
                    "id": 42,
                    "student_number": "S042",
                    "name": "Aino Example",
                    "group_name": "TT21A",
                    "programme": "Business IT",
                    "start_date": "2024-09-01",
                    "status": "ACTIVE",
                    "programme_code": "BIT",
                }
            )
        raise AssertionError(f"Unexpected query: {query}")

    def close(self) -> None:
        self.closed = True


def test_progress_agent_uses_concrete_mcp_gateway_tools_services_and_repository(
    monkeypatch,
):
    """Agent -> gateway -> MCP tools -> service -> repository boundary."""

    sessions: list[_AcademicToolSession] = []

    def make_session() -> _AcademicToolSession:
        session = _AcademicToolSession()
        sessions.append(session)
        return session

    monkeypatch.setattr("app.db.database.SessionLocal", make_session)

    result = asyncio.run(
        ProgressAnalysisAgent().run(SimpleNamespace(student_id=42))
    )

    assert result.status == "PARTIAL"
    assert result.route == "progress"
    assert result.data["student_id"] == 42
    assert result.data["completed_ects"] == 60
    assert result.data["expected_ects"] == 90
    assert result.data["progress_status"] == "BEHIND"
    assert len(sessions) == 2
    assert all(session.closed for session in sessions)
    assert any("FROM students" in query for session in sessions for query in session.queries)
    assert any("FROM curriculum" in query for session in sessions for query in session.queries)
