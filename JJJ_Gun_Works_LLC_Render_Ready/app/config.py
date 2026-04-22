from functools import lru_cache
from typing import List
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application and PostgreSQL settings loaded from environment variables.

    Primary connection mechanism: a full libpq URI in ``DATABASE_URL`` (the
    form Render provides for its managed Postgres service).

    Optional fallback: discrete ``PG_*`` variables are combined into a DSN
    when ``DATABASE_URL`` is not set — convenient for local development
    against a Docker Postgres.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Firearms Inventory API"
    app_env: str = "local"
    api_prefix: str = "/api"
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    # Primary: full libpq URI (e.g., Render DATABASE_URL).
    database_url: str | None = None

    # Optional fallback if DATABASE_URL is unset.
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "firearms_inventory"
    pg_user: str = "firearms_app"
    pg_password: str | None = None
    pg_sslmode: str = "prefer"
    pg_timeout_seconds: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def dsn(self) -> str:
        if self.database_url:
            return self.database_url
        user = quote_plus(self.pg_user)
        pwd = quote_plus(self.pg_password) if self.pg_password else ""
        auth = f"{user}:{pwd}@" if pwd else f"{user}@"
        return (
            f"postgresql://{auth}{self.pg_host}:{self.pg_port}/{self.pg_database}"
            f"?sslmode={self.pg_sslmode}&connect_timeout={self.pg_timeout_seconds}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
