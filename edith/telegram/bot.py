"""Telegram application builder and polling entry point."""

import logging
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from edith.config import Config
from edith.telegram.handlers import TelegramBotManager

logger = logging.getLogger("edith.telegram")


def build_application(manager: TelegramBotManager, token: str) -> Application:
    """Build and configure the Telegram application."""
    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", manager.handle_start))
    app.add_handler(CommandHandler("clear", manager.handle_clear))
    app.add_handler(CommandHandler("reset", manager.handle_clear))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manager.handle_message))

    # Approval gate buttons
    app.add_handler(CallbackQueryHandler(manager.handle_callback_query))

    return app
