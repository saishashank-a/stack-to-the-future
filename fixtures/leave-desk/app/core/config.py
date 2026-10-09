"""Settings for Leave Desk, read from environment variables and .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./leave_desk.db"
    broker_url: str = "redis://localhost:6379/0"
    smtp_host: str = "localhost"
    smtp_user: str = "leave-desk"
    # Fake value for tests: redaction must keep it out of every output.
    smtp_password: str = "FAKE-smtp-pass-9f8a7b6c5d4e3f2a1b0c"
    hr_inbox: str = "hr@example.com"
    direct_approval_max_days: float = 1
    self_approval_max_days: float = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
