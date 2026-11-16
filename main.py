"""Main entry point for EDITH 2.0 Telegram bot."""

import logging
import sys
from pathlib import Path

from edith.agent.loop import AgentLoop
from edith.config import load_config
from edith.logging import AuditLogger
from edith.telegram.bot import build_application
from edith.telegram.handlers import TelegramBotManager
from edith.tools.base import ToolRegistry
from edith.tools.drive import (
    DriveServiceManager,
    FetchFileTool,
    SearchDriveTool,
    SendFileTool,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("edith.main")


def main() -> None:
    """Bootstraps EDITH 2.0 agent and starts polling Telegram."""
    config = load_config()

    # Pre-flight check on required credentials
    missing = []
    if not config.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN (obtain from @BotFather)")
    if not config.telegram_user_id:
        missing.append("TELEGRAM_USER_ID (obtain your ID from @userinfobot)")
    if not config.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY (obtain from Anthropic Console)")

    if missing:
        logger.error("Missing required environment variables in .env:")
        for m in missing:
            logger.error(f"  - {m}")
        logger.error("Please copy .env.example to .env and fill in the required keys.")
        sys.exit(1)

    audit_logger = AuditLogger(log_path=config.log_file)
    logger.info(f"Audit log initialized at: {config.log_file}")

    # Set up Google Drive tools
    drive_mgr = DriveServiceManager(
        credentials_path=config.google_credentials_file,
        token_path=config.google_token_file,
    )
    search_tool = SearchDriveTool(service_manager=drive_mgr)
    fetch_tool = FetchFileTool(service_manager=drive_mgr, max_size_bytes=config.max_download_size_bytes)
    send_tool = SendFileTool(fetch_tool=fetch_tool)

    # Register tools
    registry = ToolRegistry()
    registry.register(search_tool)
    registry.register(fetch_tool)
    registry.register(send_tool)

    logger.info(f"Registered {len(registry.get_all_schemas())} tools with Agent Loop.")

    # Initialize Agent Loop
    agent_loop = AgentLoop(
        tool_registry=registry,
        api_key=config.anthropic_api_key,
        model=config.anthropic_model,
        max_iterations=config.max_agent_iterations,
        audit_logger=audit_logger,
    )

    # Initialize Telegram Manager
    manager = TelegramBotManager(
        config=config,
        agent_loop=agent_loop,
        audit_logger=audit_logger,
    )

    app = build_application(manager, config.telegram_bot_token)

    logger.info("=" * 50)
    logger.info("EDITH 2.0 is starting with long polling...")
    logger.info(f"Allowlisted Telegram User ID: {config.telegram_user_id}")
    logger.info("=" * 50)

    app.run_polling()


if __name__ == "__main__":
    main()

