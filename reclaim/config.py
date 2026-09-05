"""Application configuration loaded from environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

ENV_FILE_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Central config — loaded from .env file or environment variables."""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./reclaim.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Gemini LLM
    GEMINI_API_KEY: str = ""

    # Provider setting
    LLM_PROVIDER: str = "gemini"  # "gemini" | "groq"
    GROQ_API_KEY: str = ""

    # App
    APP_ENV: str = "dev"  # "dev" | "prod"

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "dev"

    # Alembic needs a sync URL for migrations
    @property
    def sync_database_url(self) -> str:
        return self.DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH) if ENV_FILE_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

