from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "AI Academic Copilot"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = True

    database_url: str
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: str
    telegram_webhook_enabled: bool = False
    telegram_bot_token: str
    backend_base_url: str = "http://127.0.0.1:8000"


    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()