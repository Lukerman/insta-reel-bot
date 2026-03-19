"""
Centralized configuration loader.
Reads settings from .env file and validates required variables.
Supports multiple target Instagram accounts.
"""

import os
import sys
from dotenv import load_dotenv


class Config:
    """Loads and validates all configuration from environment variables."""

    def __init__(self):
        load_dotenv()

        # Instagram target accounts (multiple)
        self.target_accounts = self._load_target_accounts()

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

    def _load_target_accounts(self) -> list[dict]:
        """
        Load target accounts from numbered env vars.
        Looks for IG_USERNAME_1/IG_PASSWORD_1, IG_USERNAME_2/IG_PASSWORD_2, etc.
        Falls back to single IG_USERNAME/IG_PASSWORD if no numbered accounts found.
        """
        accounts = []

        # Try numbered accounts: IG_USERNAME_1, IG_USERNAME_2, ...
        i = 1
        while True:
            username = os.getenv(f"IG_USERNAME_{i}")
            password = os.getenv(f"IG_PASSWORD_{i}")

            if not username:
                break

            if not password:
                print(f"❌ IG_USERNAME_{i} is set but IG_PASSWORD_{i} is missing.")
                sys.exit(1)

            if not username.startswith("your_"):
                accounts.append({"username": username, "password": password})

            i += 1

        # Fallback to single-account format
        if not accounts:
            username = os.getenv("IG_USERNAME")
            password = os.getenv("IG_PASSWORD")
            if username and password and not username.startswith("your_"):
                accounts.append({"username": username, "password": password})

        if not accounts:
            print("❌ No target accounts configured. Set IG_USERNAME_1/IG_PASSWORD_1 in .env.")
            sys.exit(1)

        return accounts

    def _require(self, key: str) -> str:
        """Get a required env variable or exit with an error."""
        value = os.getenv(key)
        if not value or value.startswith("your_"):
            print(f"❌ Missing or placeholder value for {key} in .env file.")
            sys.exit(1)
        return value

    def __repr__(self) -> str:
        account_names = [a["username"] for a in self.target_accounts]
        return (
            f"Config(\n"
            f"  target_accounts={account_names},\n"
            f"  source_accounts={self.source_accounts},\n"
            f"  check_interval={self.check_interval_minutes}min,\n"
            f"  upload_delay={self.upload_delay_minutes}min,\n"
            f"  max_reels_per_cycle={self.max_reels_per_cycle}\n"
            f")"
        )
