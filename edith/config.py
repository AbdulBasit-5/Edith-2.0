"""Configuration management for EDITH 2.0."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env file from project root if it exists
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config(BaseModel):
    """Runtime configuration validated with Pydantic."""

    telegram_bot_token: str = Field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""),
        description="Bot token from Telegram @BotFather",
    )
    telegram_user_id: int = Field(
        default_factory=lambda: int(os.getenv("TELEGRAM_USER_ID", "0")),
        description="Numerical user ID for the single-user allowlist",
    )
    anthropic_api_key: str = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""),
        description="Anthropic Claude API key",
    )
    anthropic_model: str = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
        description="Model to use for agent reasoning",
    )
    google_credentials_file: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
        description="Path to OAuth2 credentials.json file",
    )
    google_token_file: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_TOKEN_FILE", "token.json"),
        description="Path to stored OAuth2 token.json file",
    )
    log_file: str = Field(
        default_factory=lambda: os.getenv("LOG_FILE", "logs/edith.jsonl"),
        description="Destination path for structured JSON audit logs",
    )
    max_agent_iterations: int = Field(
        default=6,
        description="Maximum iterations the agent loop can run per message to prevent runaway loops",
    )
    max_download_size_bytes: int = Field(
        default=25 * 1024 * 1024,
        description="Maximum file size in bytes to fetch from Drive (25MB safety cap)",
    )


def load_config() -> Config:
    """Load and return the validated application configuration."""
    return Config()
