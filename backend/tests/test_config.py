"""Focused tests for the canonical application configuration."""

from pathlib import Path

import pytest

from app.core.config import PROJECT_DIR, Settings


def test_settings_can_load_without_external_credentials(monkeypatch):
    for name in (
        "DATABASE_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("sqlite:///")
    assert settings.telegram_bot_token == ""
    assert settings.gemini_api_key == ""


def test_rag_defaults_are_project_relative():
    settings = Settings(_env_file=None)

    assert settings.knowledge_base_dir == PROJECT_DIR / "docs" / "knowledge_base"
    assert settings.rag_evaluation_dataset == (
        PROJECT_DIR / "rag" / "evaluation" / "evaluation_dataset.json"
    )
    assert settings.rag_evaluation_reports_dir == (
        PROJECT_DIR / "rag" / "evaluation" / "reports"
    )


def test_external_service_settings_are_configurable(monkeypatch, tmp_path: Path):
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setenv("QDRANT_URL", "http://qdrant.internal:6333")
    monkeypatch.setenv("QDRANT_COLLECTION_NAME", "test_collection")
    monkeypatch.setenv("KNOWLEDGE_BASE_DIR", str(knowledge_dir))

    settings = Settings(_env_file=None)

    assert settings.qdrant_url == "http://qdrant.internal:6333"
    assert settings.qdrant_collection_name == "test_collection"
    assert settings.knowledge_base_dir == knowledge_dir


def test_enabled_telegram_webhook_requires_credentials(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_ENABLED", "true")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Settings(_env_file=None)


def test_daily_workflow_schedule_is_configurable(monkeypatch):
    monkeypatch.setenv("DAILY_WORKFLOW_HOUR", "7")
    monkeypatch.setenv("DAILY_WORKFLOW_MINUTE", "30")
    monkeypatch.setenv("DAILY_WORKFLOW_TIMEZONE", "Europe/Helsinki")

    settings = Settings(_env_file=None)

    assert settings.daily_workflow_hour == 7
    assert settings.daily_workflow_minute == 30
    assert settings.daily_workflow_timezone == "Europe/Helsinki"
