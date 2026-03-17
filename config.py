"""
Centralized configuration loader.
Reads settings from .env file and validates required variables.
"""

import os
import sys
from dotenv import load_dotenv


class Config:
    """Loads and validates all configuration from environment variables."""

    def __init__(self):
        load_dotenv()

        # Instagram credentials
        self.ig_username = self._require("IG_USERNAME")
        self.ig_password = self._require("IG_PASSWORD")

        # Telegram credentials
        self.telegram_bot_token = self._require("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = self._require("TELEGRAM_CHAT_ID")

        # Source accounts
        raw_accounts = self._require("SOURCE_ACCOUNTS")
        self.source_accounts = [a.strip() for a in raw_accounts.split(",") if a.strip()]

        # Timing
        self.check_interval_minutes = int(os.getenv("CHECK_INTERVAL_MINUTES", "360"))
        self.upload_delay_minutes = int(os.getenv("UPLOAD_DELAY_MINUTES", "30"))
        self.max_reels_per_cycle = int(os.getenv("MAX_REELS_PER_CYCLE", "5"))
        self.batch_size = int(os.getenv("BATCH_SIZE", "3"))

        # Caption
        self.caption_template = os.getenv("CAPTION_TEMPLATE", "🎬 Reposted | Credit: @{source}")

        # Paths
        self.download_dir = os.path.join(os.path.dirname(__file__), "downloads")
        self.db_path = os.path.join(os.path.dirname(__file__), "reels.db")

        # Ensure downloads directory exists
        os.makedirs(self.download_dir, exist_ok=True)

    def _require(self, key: str) -> str:
        """Get a required env variable or exit with an error."""
        value = os.getenv(key)
        if not value or value.startswith("your_"):
            print(f"❌ Missing or placeholder value for {key} in .env file.")
            sys.exit(1)
        return value

    def __repr__(self) -> str:
        return (
            f"Config(\n"
            f"  ig_username={self.ig_username},\n"
            f"  source_accounts={self.source_accounts},\n"
            f"  check_interval={self.check_interval_minutes}min,\n"
            f"  upload_delay={self.upload_delay_minutes}min,\n"
            f"  max_reels_per_cycle={self.max_reels_per_cycle}\n"
            f")"
        )
