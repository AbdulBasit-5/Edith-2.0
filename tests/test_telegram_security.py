"""Tests for Telegram security allowlist: ensuring only the authorized user ID is accepted."""

from edith.config import Config
from edith.telegram.handlers import TelegramBotManager


class MockUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class MockUpdate:
    def __init__(self, user_id: int, text: str = "Hello") -> None:
        self.effective_user = MockUser(user_id)


class MockAgentLoop:
    def __init__(self) -> None:
        self.called = False

    def run(self, *args, **kwargs):
        self.called = True
        return None


class MockAuditLogger:
    def log_approval(self, *args, **kwargs):
        pass


def test_telegram_allowlist_enforcement():
    config = Config(telegram_user_id=123456789)
    manager = TelegramBotManager(config, MockAgentLoop(), MockAuditLogger())

    # 1. Allowed user ID passes
    allowed_update = MockUpdate(user_id=123456789)
    assert manager.is_authorized(allowed_update) is True

    # 2. Rogue / unauthorized user ID is rejected
    unauthorized_update = MockUpdate(user_id=999999999)
    assert manager.is_authorized(unauthorized_update) is False

    # 3. None user is rejected
    none_update = MockUpdate(user_id=0)
    none_update.effective_user = None
    assert manager.is_authorized(none_update) is False
