from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            "/home/deepanshu/config/shared.env",
            "/home/deepanshu/config/shared.secrets.env",
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_token: str = Field(
        default="",
        validation_alias=AliasChoices("DISCORD_BOT_TOKEN", "DISCORD_TOKEN"),
    )
    receipt_channel_id: int = Field(default=0, alias="RECEIPT_CHANNEL_ID")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_receipt_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_RECEIPT_MODEL", "OPENAI_MODEL"),
    )
    openai_correction_model: str = Field(default="gpt-4o-mini", alias="OPENAI_CORRECTION_MODEL")
    database_path: Path = Field(default=Path("data/expenses.sqlite"), alias="DATABASE_PATH")
    image_dir: Path = Field(default=Path("data/images"), alias="IMAGE_DIR")
    max_image_bytes: int = Field(default=8 * 1024 * 1024, alias="MAX_IMAGE_BYTES")
    default_currency: str = Field(default="THB", alias="DEFAULT_CURRENCY")
    otel_service_name: str = Field(default="expense-tracker", alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://otel-collector:4318",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_enabled: bool = Field(default=True, alias="OTEL_ENABLED")

    @model_validator(mode="after")
    def require_runtime_secrets(self) -> Settings:
        missing: list[str] = []
        if not self.discord_token:
            missing.append("DISCORD_TOKEN")
        if self.receipt_channel_id <= 0:
            missing.append("RECEIPT_CHANNEL_ID")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        return self


def load_settings() -> Settings:
    return Settings()
