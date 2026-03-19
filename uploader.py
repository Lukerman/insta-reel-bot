"""
Reel uploader — uploads downloaded reels to target Instagram accounts.
Supports multiple target accounts with independent sessions.
Uses instagrapi for authenticated Instagram API access.
"""

import gc
import glob
import os
import time
import logging
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    ChallengeRequired,
    FeedbackRequired,
    PleaseWaitFewMinutes,
)

from database import Database

logger = logging.getLogger(__name__)

SESSION_DIR = os.path.dirname(__file__)


class ReelUploader:
    """Uploads reels to a single target Instagram account."""

    def __init__(self, db: Database, username: str, password: str, caption_template: str):
        self.db = db
        self.username = username
        self.password = password
        self.caption_template = caption_template
        self.client = Client()
        self.client.delay_range = [2, 5]  # Random delay between API calls
        self._login()

    def _session_file(self) -> str:
        return os.path.join(SESSION_DIR, f"ig_session_{self.username}.json")

    def _login(self):
        """Log in to Instagram, reusing session if available."""
        session_file = self._session_file()
        try:
            if os.path.exists(session_file):
                logger.info(f"🔑 [{self.username}] Loading saved session...")
                self.client.load_settings(session_file)
                self.client.login(self.username, self.password)
                try:
                    self.client.account_info()
                    logger.info(f"✅ [{self.username}] Session restored.")
                    return
                except LoginRequired:
                    logger.warning(f"⚠️ [{self.username}] Session expired, fresh login...")

            logger.info(f"🔐 [{self.username}] Logging into Instagram...")
            self.client.login(self.username, self.password)
            self.client.dump_settings(session_file)
            logger.info(f"✅ [{self.username}] Logged in and session saved.")

        except ChallengeRequired:
            logger.error(f"❌ [{self.username}] Challenge required! Log in manually first.")
            raise
        except Exception as e:
            logger.error(f"❌ [{self.username}] Login failed: {e}")
            raise

    def upload_reel(self, reel: dict) -> bool:
        """
        Upload a single reel. Returns True on success, False on failure.
        Updates the database status and target_account accordingly.
        """
        shortcode = reel["shortcode"]
        local_path = reel["local_path"]
        source = reel["source_account"]

        if not local_path or not os.path.exists(local_path):
            logger.warning(f"⚠️ [{self.username}] File not found for {shortcode}: {local_path}")
            self.db.update_status(shortcode, "failed", error_message="File not found")
            return False

        try:
            logger.info(f"📤 [{self.username}] Uploading reel: {shortcode} from @{source}...")
            caption = self.caption_template.replace("{source}", source)
            media = self.client.clip_upload(Path(local_path), caption=caption)

            self.db.update_status(shortcode, "uploaded", target_account=self.username)
            logger.info(f"  ✅ [{self.username}] Uploaded {shortcode} (media ID: {media.pk})")

            # Delete the video file and any associated thumbnails
            self._delete_file(local_path)
            self._delete_related_files(local_path)
            return True

        except PleaseWaitFewMinutes:
            logger.warning(f"  ⏳ [{self.username}] Rate limited!")
            self.db.update_status(shortcode, "downloaded")  # Keep for retry
            return False
        except FeedbackRequired as e:
            logger.error(f"  ❌ [{self.username}] Feedback required for {shortcode}: {e}")
            self.db.update_status(shortcode, "failed", error_message=f"Feedback: {e}")
            return False
        except Exception as e:
            logger.error(f"  ❌ [{self.username}] Upload failed for {shortcode}: {e}")
            self.db.update_status(shortcode, "failed", error_message=str(e))
            return False

    def _delete_file(self, filepath: str, retries: int = 3, delay: float = 2.0):
        """Delete a file with retries to handle Windows file locking."""
        for attempt in range(retries):
            try:
                gc.collect()
                time.sleep(delay)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logger.info(f"  🗑️ Deleted: {filepath}")
                return
            except PermissionError:
                logger.warning(f"  ⏳ File locked, retry {attempt + 1}/{retries}...")
            except Exception as e:
                logger.warning(f"  ⚠️ Delete failed: {e}")
                return
        logger.warning(f"  ⚠️ Could not delete {filepath} after {retries} attempts")

    def _delete_related_files(self, filepath: str):
        """Delete thumbnail/related files created by instagrapi (e.g., .mp4.jpg)."""
        for related in glob.glob(f"{filepath}.*"):
            try:
                os.remove(related)
                logger.info(f"  🗑️ Deleted related file: {related}")
            except Exception as e:
                logger.warning(f"  ⚠️ Failed to delete related file {related}: {e}")


class UploaderManager:
    """Manages multiple ReelUploader instances for multi-account uploads."""

    def __init__(self, db: Database, target_accounts: list[dict], caption_template: str):
        self.db = db
        self.caption_template = caption_template
        self.uploaders: list[ReelUploader] = []
        self._upload_index = 0  # Round-robin counter

        for account in target_accounts:
            try:
                uploader = ReelUploader(
                    db=db,
                    username=account["username"],
                    password=account["password"],
                    caption_template=caption_template,
                )
                self.uploaders.append(uploader)
            except Exception as e:
                logger.error(f"❌ Failed to initialize uploader for @{account['username']}: {e}")

        if not self.uploaders:
            logger.error("❌ No target accounts could be initialized!")
            raise RuntimeError("No target accounts available")

        logger.info(f"✅ UploaderManager ready with {len(self.uploaders)} account(s): "
                     f"{[u.username for u in self.uploaders]}")

    def get_first_client(self) -> Client:
        """Return the first available authenticated client (for scraper use)."""
        return self.uploaders[0].client

    def get_account_names(self) -> list[str]:
        """Return list of target account usernames."""
        return [u.username for u in self.uploaders]

    def upload_pending(self, limit: int = 6, delay_minutes: int = 30, batch_size: int = 3) -> list[dict]:
        """
        Upload pending reels distributed round-robin across target accounts.
        Returns list of successfully uploaded reel dicts.
        """
        pending = self.db.get_pending_uploads(limit=limit)
        uploaded = []
        rate_limited_accounts = set()

        for i, reel in enumerate(pending):
            # Skip if all accounts are rate-limited
            if len(rate_limited_accounts) >= len(self.uploaders):
                logger.warning("⚠️ All target accounts rate-limited. Stopping uploads.")
                break

            # Pick the next available uploader (round-robin, skip rate-limited)
            uploader = self._get_next_uploader(rate_limited_accounts)
            if uploader is None:
                break

            success = uploader.upload_reel(reel)

            if success:
                reel["target_account"] = uploader.username
                uploaded.append(reel)

                # Batch delay: after every batch_size uploads, wait
                batch_pos = (len(uploaded)) % batch_size
                if batch_pos == 0 and i < len(pending) - 1:
                    logger.info(f"  📦 Batch of {batch_size} done. Waiting {delay_minutes} mins...")
                    time.sleep(delay_minutes * 60)
            else:
                # Check if it was a rate limit (status kept as 'downloaded')
                row = self.db.conn.execute(
                    "SELECT status FROM reels WHERE shortcode = ?", (reel["shortcode"],)
                ).fetchone()
                if row and row["status"] == "downloaded":
                    # Rate limited — mark this account
                    rate_limited_accounts.add(uploader.username)

        logger.info(f"📊 Upload complete. {len(uploaded)}/{len(pending)} successful.")
        return uploaded

    def _get_next_uploader(self, skip_accounts: set) -> ReelUploader | None:
        """Get the next uploader in round-robin order, skipping rate-limited ones."""
        tried = 0
        while tried < len(self.uploaders):
            uploader = self.uploaders[self._upload_index % len(self.uploaders)]
            self._upload_index += 1
            if uploader.username not in skip_accounts:
                return uploader
            tried += 1
        return None
