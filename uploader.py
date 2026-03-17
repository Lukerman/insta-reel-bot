"""
Reel uploader — uploads downloaded reels to the target Instagram account.
Uses instagrapi for authenticated Instagram API access.
"""

import gc
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

SESSION_FILE = os.path.join(os.path.dirname(__file__), "ig_session.json")


class ReelUploader:
    """Uploads reels to the target Instagram account."""

    def __init__(self, db: Database, username: str, password: str, caption_template: str):
        self.db = db
        self.username = username
        self.password = password
        self.caption_template = caption_template
        self.client = Client()
        self.client.delay_range = [2, 5]  # Random delay between API calls
        self._login()

    def _login(self):
        """Log in to Instagram, reusing session if available."""
        try:
            if os.path.exists(SESSION_FILE):
                logger.info("🔑 Loading saved Instagram session...")
                self.client.load_settings(SESSION_FILE)
                self.client.login(self.username, self.password)
                try:
                    self.client.account_info()
                    logger.info("✅ Session restored successfully.")
                    return
                except LoginRequired:
                    logger.warning("⚠️ Saved session expired, performing fresh login...")

            logger.info("🔐 Logging into Instagram...")
            self.client.login(self.username, self.password)
            self.client.dump_settings(SESSION_FILE)
            logger.info("✅ Logged in and session saved.")

        except ChallengeRequired:
            logger.error("❌ Instagram challenge required! Please log in manually first.")
            raise
        except Exception as e:
            logger.error(f"❌ Login failed: {e}")
            raise

    def upload_pending(self, limit: int = 6, delay_minutes: int = 30, batch_size: int = 3) -> list[dict]:
        """
        Upload pending reels (status='downloaded') in batches.
        Uploads batch_size reels back-to-back, then waits delay_minutes before the next batch.
        Returns list of successfully uploaded reel dicts.
        """
        pending = self.db.get_pending_uploads(limit=limit)
        uploaded = []
        rate_limited = False

        for i, reel in enumerate(pending):
            if rate_limited:
                break

            shortcode = reel["shortcode"]
            local_path = reel["local_path"]
            source = reel["source_account"]

            # Check file exists
            if not local_path or not os.path.exists(local_path):
                logger.warning(f"⚠️ File not found for {shortcode}: {local_path}")
                self.db.update_status(shortcode, "failed", error_message="File not found")
                continue

            try:
                logger.info(f"📤 Uploading reel {i+1}/{len(pending)}: {shortcode} from @{source}...")

                caption = self.caption_template.replace("{source}", source)
                media = self.client.clip_upload(
                    Path(local_path),
                    caption=caption,
                )

                self.db.update_status(shortcode, "uploaded")
                reel["ig_media_id"] = str(media.pk)
                uploaded.append(reel)
                logger.info(f"  ✅ Uploaded reel {shortcode} (media ID: {media.pk})")

                # Delete the video file after successful upload
                self._delete_file(local_path)

                # After every batch_size uploads, wait delay_minutes (skip after the last reel)
                batch_pos = (i + 1) % batch_size
                if batch_pos == 0 and i < len(pending) - 1:
                    logger.info(f"  📦 Batch of {batch_size} done. Waiting {delay_minutes} minutes before next batch...")
                    time.sleep(delay_minutes * 60)

            except PleaseWaitFewMinutes:
                logger.warning(f"  ⏳ Rate limited! Stopping uploads for this cycle.")
                self.db.update_status(shortcode, "downloaded")  # Keep for retry
                rate_limited = True
            except FeedbackRequired as e:
                logger.error(f"  ❌ Instagram feedback required for {shortcode}: {e}")
                self.db.update_status(shortcode, "failed", error_message=f"Feedback: {e}")
            except Exception as e:
                logger.error(f"  ❌ Upload failed for {shortcode}: {e}")
                self.db.update_status(shortcode, "failed", error_message=str(e))

        logger.info(f"📊 Upload complete. {len(uploaded)}/{len(pending)} successful.")
        return uploaded

    def _delete_file(self, filepath: str, retries: int = 3, delay: float = 2.0):
        """Delete a file with retries to handle Windows file locking."""
        for attempt in range(retries):
            try:
                gc.collect()  # Force release any lingering file handles
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
