"""Tests for configuration loading and validation."""

import os
from edith.config import Config, load_config


def test_config_defaults(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_USER_ID", "987654321")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    config = load_config()
    assert config.telegram_bot_token == "123:ABC"
    assert config.telegram_user_id == 987654321
    assert config.anthropic_api_key == "sk-ant-test"
    assert config.max_agent_iterations == 6
    assert config.max_download_size_bytes == 25 * 1024 * 1024

