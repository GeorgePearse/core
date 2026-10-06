"""Typed runtime settings for the standalone viewer API."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the standalone viewer API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    agentic_vision_viewer_runs_dir: str = Field(
        default="/tmp/agentic-vision-viewer-runs",
        validation_alias="AGENTIC_VISION_VIEWER_RUNS_DIR",
    )
    dashscope_api_key: str | None = Field(default=None, validation_alias="DASHSCOPE_API_KEY")
    dashscope_api_base: str = Field(
        default="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        validation_alias="DASHSCOPE_API_BASE",
    )
    qwen_model: str = Field(default="qwen3-vl-plus", validation_alias="QWEN_MODEL")
    api_host: str = Field(default="127.0.0.1", validation_alias="AGENTIC_VISION_VIEWER_API_HOST")
    api_port: int = Field(default=8000, validation_alias="AGENTIC_VISION_VIEWER_API_PORT")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="AGENTIC_VISION_VIEWER_CORS_ORIGINS",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Return configured CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached API settings."""
    return Settings()
