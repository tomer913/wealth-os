from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Literal


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str

    # Async variant – swap postgres:// → postgresql+asyncpg://
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://"
        ).replace(
            "postgres://", "postgresql+asyncpg://"
        )

    # ── Supabase ──────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # ── App ───────────────────────────────────────────────────
    SECRET_KEY: str = "dev-secret-change-in-production"
    ENVIRONMENT: Literal["development", "staging", "production"] = "production"

    # ── Defaults ──────────────────────────────────────────────
    DEFAULT_CURRENCY: str = "ILS"
    APP_TITLE: str = "Wealth OS API"
    APP_VERSION: str = "0.1.0"

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must be set")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
