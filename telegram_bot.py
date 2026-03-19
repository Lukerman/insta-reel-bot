"""
Telegram bot — sends status updates and handles user commands.
Commands: /status, /recent, /pause, /resume, /help
Supports multi-account target display.
"""

import logging
import asyncio
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from database import Database

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram bot for status notifications and control commands."""

    def __init__(self, bot_token: str, chat_id: str, db: Database, target_accounts: list[str] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.db = db
        self.paused = False
        self.target_accounts = target_accounts or []
        self._app = None
        self._bot = Bot(token=bot_token)

    async def send_message(self, text: str):
        """Send a message to the configured chat."""
        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram message: {e}")

    async def notify_startup(self):
        accounts_str = ", ".join(f"@{a}" for a in self.target_accounts) if self.target_accounts else "N/A"
        await self.send_message(
            "🤖 <b>Instagram Reel Bot Started</b>\n\n"
            f"Target accounts: {accounts_str}\n"
            f"Total targets: <b>{len(self.target_accounts)}</b>\n\n"
            "Bot is now monitoring source accounts.\n"
            "Use /help to see available commands."
        )

    async def notify_scan_results(self, new_count: int, source_accounts: list[str]):
        accounts_str = ", ".join(f"@{a}" for a in source_accounts)
        await self.send_message(
            f"🔍 <b>Scan Complete</b>\n\n"
            f"Accounts scanned: {accounts_str}\n"
            f"New reels found: <b>{new_count}</b>"
        )

    async def notify_download(self, shortcode: str, source: str, success: bool):
        if success:
            await self.send_message(
                f"⬇️ <b>Downloaded</b>\n"
                f"Reel <code>{shortcode}</code> from @{source}"
            )
        else:
            await self.send_message(
                f"❌ <b>Download Failed</b>\n"
                f"Reel <code>{shortcode}</code> from @{source}"
            )

    async def notify_upload(self, shortcode: str, source: str, success: bool, target_account: str = None):
        target_str = f" → @{target_account}" if target_account else ""
        if success:
            await self.send_message(
                f"📤 <b>Uploaded!</b>\n"
                f"Reel <code>{shortcode}</code> from @{source}{target_str} ✅"
            )
        else:
            await self.send_message(
                f"❌ <b>Upload Failed</b>\n"
                f"Reel <code>{shortcode}</code> from @{source}{target_str}"
            )

    async def notify_cycle_summary(self, discovered: int, downloaded: int, uploaded: int):
        stats = self.db.get_stats()
        target_stats = self.db.get_stats_by_target()

        # Build per-account breakdown
        target_lines = ""
        if target_stats:
            target_lines = "\n<b>Uploads by Account:</b>\n"
            for account, count in target_stats.items():
                target_lines += f"  📱 @{account}: {count}\n"

        await self.send_message(
            f"📊 <b>Cycle Summary</b>\n\n"
            f"New reels discovered: {discovered}\n"
            f"Downloaded: {downloaded}\n"
            f"Uploaded: {uploaded}\n\n"
            f"<b>Total Stats:</b>\n"
            f"  📥 Discovered: {stats.get('discovered', 0)}\n"
            f"  💾 Downloaded: {stats.get('downloaded', 0)}\n"
            f"  ✅ Uploaded: {stats.get('uploaded', 0)}\n"
            f"  ❌ Failed: {stats.get('failed', 0)}\n"
            f"  📁 Total: {stats.get('total', 0)}"
            f"{target_lines}"
        )

    async def notify_error(self, error_msg: str):
        await self.send_message(f"🚨 <b>Error</b>\n\n{error_msg}")

    # --- Command Handlers ---

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats = self.db.get_stats()
        target_stats = self.db.get_stats_by_target()
        paused_text = "⏸️ PAUSED" if self.paused else "▶️ RUNNING"

        # Per-account breakdown
        target_lines = ""
        if target_stats:
            target_lines = "\n<b>Uploads by Account:</b>\n"
            for account, count in target_stats.items():
                target_lines += f"  📱 @{account}: {count}\n"

        accounts_str = ", ".join(f"@{a}" for a in self.target_accounts) if self.target_accounts else "N/A"

        await update.message.reply_text(
            f"📊 <b>Bot Status: {paused_text}</b>\n\n"
            f"Target accounts: {accounts_str}\n\n"
            f"📥 Pending download: {stats.get('discovered', 0)}\n"
            f"💾 Pending upload: {stats.get('downloaded', 0)}\n"
            f"✅ Uploaded: {stats.get('uploaded', 0)}\n"
            f"❌ Failed: {stats.get('failed', 0)}\n"
            f"📁 Total tracked: {stats.get('total', 0)}"
            f"{target_lines}",
            parse_mode="HTML",
        )

    async def _cmd_recent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        recent = self.db.get_recent(limit=5)
        if not recent:
            await update.message.reply_text("No reels tracked yet.")
            return

        lines = ["📋 <b>Recent Reels</b>\n"]
        status_icons = {
            "discovered": "🔍", "downloaded": "💾",
            "uploaded": "✅", "failed": "❌",
        }
        for r in recent:
            icon = status_icons.get(r["status"], "❓")
            target_str = f" → @{r['target_account']}" if r.get("target_account") else ""
            lines.append(
                f"{icon} <code>{r['shortcode']}</code> "
                f"from @{r['source_account']}{target_str} — {r['status']}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.paused = True
        await update.message.reply_text("⏸️ Bot paused. Use /resume to continue.")

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.paused = False
        await update.message.reply_text("▶️ Bot resumed!")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 <b>Available Commands</b>\n\n"
            "/status — Show current bot stats\n"
            "/recent — Show last 5 tracked reels\n"
            "/pause — Pause the bot\n"
            "/resume — Resume the bot\n"
            "/help — Show this message",
            parse_mode="HTML",
        )

    def build_app(self):
        """Build the telegram Application with command handlers."""
        self._app = ApplicationBuilder().token(self.bot_token).build()
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("recent", self._cmd_recent))
        self._app.add_handler(CommandHandler("pause", self._cmd_pause))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        return self._app
