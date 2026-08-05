from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    app_name: str = "AI Academic Copilot"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = True

    database_url: str = "sqlite:///./academic_copilot.db"
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: str = ""
    telegram_webhook_enabled: bool = False
    telegram_bot_token: str = ""
    internal_service_key: str = ""
    backend_base_url: str = "http://127.0.0.1:8000"
    gemini_api_key: str = ""
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection_name: str = "academic_knowledge"
    knowledge_base_dir: Path = PROJECT_DIR / "docs" / "knowledge_base"
    rag_evaluation_dataset: Path = (
        PROJECT_DIR / "rag" / "evaluation" / "evaluation_dataset.json"
    )
    rag_evaluation_reports_dir: Path = PROJECT_DIR / "rag" / "evaluation" / "reports"

    # Scheduler configuration
    # Controls whether the in-process scheduler is enabled. Default is disabled
    # to avoid starting background jobs during tests or in environments that do
    # not require scheduled workflows.
    scheduler_enabled: bool = False
    # Timezone used by the scheduler for computing job run times. Must be a
    # valid IANA timezone name (e.g. "UTC", "Europe/Helsinki"). Defaults to UTC.
    scheduler_timezone: str = "UTC"

    # Monday workflow schedule. The configured scheduler timezone is used for
    # interpretation; no server-local timezone is used.
    monday_workflow_hour: int = Field(default=6, ge=0, le=23)
    monday_workflow_minute: int = Field(default=0, ge=0, le=59)


    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_enabled_integrations(self) -> "Settings":
        if self.telegram_webhook_enabled:
            missing = [
                name
                for name, value in (
                    ("TELEGRAM_BOT_TOKEN", self.telegram_bot_token),
                    ("TELEGRAM_WEBHOOK_SECRET", self.telegram_webhook_secret),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "Telegram webhook is enabled but required settings are missing: "
                    + ", ".join(missing)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide application settings instance."""
    return Settings()


settings = get_settings()
