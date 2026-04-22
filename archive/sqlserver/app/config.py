from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application and SQL Server settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Firearms Inventory API"
    app_env: str = "local"
    api_prefix: str = "/api"
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"])

    sqlserver_driver: str = "ODBC Driver 18 for SQL Server"
    sqlserver_server: str = "localhost"
    sqlserver_database: str = "FirearmsInventory"
    sqlserver_trusted_connection: bool = True
    sqlserver_username: str | None = None
    sqlserver_password: str | None = None
    sqlserver_encrypt: str = "no"
    sqlserver_trust_server_certificate: str = "yes"
    sqlserver_timeout_seconds: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def odbc_connection_string(self) -> str:
        base = [
            f"DRIVER={{{self.sqlserver_driver}}}",
            f"SERVER={self.sqlserver_server}",
            f"DATABASE={self.sqlserver_database}",
            f"Encrypt={self.sqlserver_encrypt}",
            f"TrustServerCertificate={self.sqlserver_trust_server_certificate}",
            f"Connection Timeout={self.sqlserver_timeout_seconds}",
        ]

        if self.sqlserver_trusted_connection:
            base.append("Trusted_Connection=yes")
        else:
            if not self.sqlserver_username or not self.sqlserver_password:
                raise ValueError("SQL Server username and password are required when trusted connection is false.")
            base.extend([f"UID={self.sqlserver_username}", f"PWD={self.sqlserver_password}"])

        return ";".join(base) + ";"


@lru_cache
def get_settings() -> Settings:
    return Settings()
