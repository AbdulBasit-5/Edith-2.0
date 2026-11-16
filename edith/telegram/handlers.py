"""Telegram bot message and callback query handlers with strict allowlisting and approval gate."""

import asyncio
import logging
from typing import Dict, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from edith.agent.loop import AgentLoop
from edith.agent.state import ConversationMemory, LoopStatus, PendingApproval
from edith.config import Config
from edith.logging import AuditLogger

logger = logging.getLogger("edith.telegram")


class TelegramBotManager:
    """Manages Telegram bot lifecycle, routing, and conversation state."""

    def __init__(
        self,
        config: Config,
        agent_loop: AgentLoop,
        audit_logger: AuditLogger,
    ) -> None:
        self.config = config
        self.agent_loop = agent_loop
        self.audit_logger = audit_logger
        self.memory = ConversationMemory(max_turns=10)
        self.active_approval: Optional[PendingApproval] = None

    def is_authorized(self, update: Update) -> bool:
        """Verify that the sender matches the strict user ID allowlist."""
        user = update.effective_user
        if not user or user.id != self.config.telegram_user_id:
            user_id = user.id if user else "Unknown"
            logger.warning(f"Unauthorized message access attempt by user_id: {user_id}. Silently ignored.")
            return False
        return True

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self.is_authorized(update):
            return

        welcome_text = (
            "👋 **EDITH 2.0 Online**\n\n"
            "I'm your personal assistant connected to your Google Drive.\n"
            "Try asking:\n"
            "- _\"Find my OS lecture notes\"_\n"
            "- _\"Search Drive for resume\"_\n"
            "- _\"What's 2 + 2?\"_\n"
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

    async def handle_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clear or /reset to reset conversation memory."""
        if not self.is_authorized(update):
            return

        self.memory.clear()
        self.active_approval = None
        await update.message.reply_text("🧹 Conversation history cleared.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming text messages from the authorized user."""
        if not self.is_authorized(update):
            return

        user_text = update.message.text
        if not user_text:
            return

        # Add user message to conversation memory
        self.memory.add_user_message(user_text)

        # Show typing indicator
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing",
        )

        # Run agent loop in a separate worker thread so long polling stays responsive
        result = await asyncio.to_thread(self.agent_loop.run, self.memory)

        if result.status == LoopStatus.AWAITING_APPROVAL and result.pending_approval:
            self.active_approval = result.pending_approval
            self.audit_logger.log_approval(
                tool_name=result.pending_approval.tool_name,
                arguments=result.pending_approval.arguments,
                approved=False,  # pending
                user_id=self.config.telegram_user_id,
            )

            # Build inline buttons for approval
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, send file", callback_data="approval_yes"),
                    InlineKeyboardButton("❌ No, cancel", callback_data="approval_no"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                result.pending_approval.prompt_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        if result.final_text:
            await update.message.reply_text(result.final_text)

        if result.file_to_send and result.file_to_send.get("file_path"):
            await self._deliver_file(update, context, result.file_to_send)

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle Yes/No taps from the approval gate."""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(update):
            return

        if not self.active_approval:
            await query.edit_message_text("⚠️ No pending approval request found.")
            return

        pending = self.active_approval
        self.active_approval = None

        user_approved = (query.data == "approval_yes")

        # Log decision to audit trail
        self.audit_logger.log_approval(
            tool_name=pending.tool_name,
            arguments=pending.arguments,
            approved=user_approved,
            user_id=self.config.telegram_user_id,
        )

        decision_label = "Approved ✅" if user_approved else "Declined ❌"
        await query.edit_message_text(f"Action {decision_label}. Processing with EDITH...")

        # Resume agent loop in thread
        resume_data = {
            "tool_use_id": pending.tool_use_id,
            "tool_name": pending.tool_name,
            "approved": user_approved,
            "arguments": pending.arguments,
        }

        result = await asyncio.to_thread(self.agent_loop.run, self.memory, resume_data)

        if result.final_text:
            await query.message.reply_text(result.final_text)

        if result.file_to_send and result.file_to_send.get("file_path"):
            await self._deliver_file(update, context, result.file_to_send)

    async def _deliver_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE, file_info: dict) -> None:
        """Safely upload and send the retrieved file to the chat."""
        chat_id = update.effective_chat.id
        path = file_info.get("file_path")
        caption = file_info.get("caption") or f"📄 {file_info.get('file_name', 'Requested File')}"

        try:
            with open(path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    caption=caption,
                )
        except Exception as e:
            logger.error(f"Error sending file to Telegram: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Failed to deliver file: {str(e)}",
            )

