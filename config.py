from __future__ import annotations

import json
from functools import lru_cache
from typing import List
from urllib.parse import quote_plus

from pydantic import Field, computed_field, field_validator
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
        populate_by_name=True,
    )

    app_name: str = "Firearms Inventory API"
    app_env: str = "local"
    api_prefix: str = "/api"

    # ``cors_origins`` is stored as a raw string so pydantic-settings does
    # NOT try to JSON-decode the env value itself (that's what raised
    # ``SettingsError: error parsing value for field "cors_origins"`` when
    # Render injected ``http://a.com,http://b.com``). The parsed list is
    # exposed via the ``cors_origins`` computed property below.
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        validation_alias="CORS_ORIGINS",
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

    @field_validator("cors_origins_raw", mode="before")
    @classmethod
    def _coerce_cors_raw(cls, value: object) -> str:
        """Accept list/tuple/str/None and reduce to a single string form.

        A Python list (e.g. from programmatic construction) is re-emitted as
        a comma-separated string; a JSON array string and a comma-separated
        string are both passed through untouched and parsed in
        :attr:`cors_origins`.
        """

        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return ",".join(str(item).strip() for item in value if str(item).strip())
        return str(value)

    @computed_field  # type: ignore[misc]
    @property
    def cors_origins(self) -> List[str]:
        """Parsed CORS origins as a list of non-empty strings.

        Accepted input forms for ``CORS_ORIGINS``:

        * empty string / unset                      -> ``[]``
        * single URL                                -> ``["https://a.com"]``
        * comma-separated                           -> ``["https://a.com", "https://b.com"]``
        * JSON list literal ``["https://a.com"]``   -> ``["https://a.com"]``
        """

        raw = (self.cors_origins_raw or "").strip()
        if not raw:
            return []

        # JSON list form, e.g. '["https://a.com","https://b.com"]'.
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]

        # Comma-separated or single URL.
        return [item.strip() for item in raw.split(",") if item.strip()]

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
