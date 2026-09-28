"""Central configuration for Ragger Engine."""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    """Engine configuration loaded from environment and CLI flags."""
    
    app_name: str = "ragger-engine"
    app_version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8000
    ragger_api_token: Optional[str] = None
    environment: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = EngineSettings()
