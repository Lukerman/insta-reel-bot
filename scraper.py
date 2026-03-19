"""
Reel scraper — discovers new reels from source Instagram accounts.
Uses instagrapi (authenticated session) to avoid rate limiting.
"""

import logging
import time

from instagrapi import Client
from instagrapi.exceptions import (
    UserNotFound,
    ClientError,
    PleaseWaitFewMinutes,
)

from database import Database

logger = logging.getLogger(__name__)


class ReelScraper:
    """Scrapes Instagram profiles to discover new reels using an authenticated client."""

    def __init__(self, db: Database, client: Client):
        self.db = db
        self.client = client

    def discover_reels(self, source_accounts: list[str], max_per_account: int = 10) -> list[dict]:
        """
        Scan source accounts for new reels using the authenticated instagrapi client.
        Returns a list of newly discovered reel metadata dicts.
        """
        new_reels = []

        for username in source_accounts:
            try:
                logger.info(f"🔍 Scanning @{username} for reels...")

                # Get user ID using the private API (avoids public endpoint rate limits)
                user_info = self.client.user_info_by_username_v1(username)
                user_id = user_info.pk
                time.sleep(2)  # Small delay to be safe

                # Fetch recent clips/reels
                reels = self.client.user_clips(user_id, amount=max_per_account)
                time.sleep(2)

                for media in reels:
                    shortcode = media.code
                    if not shortcode:
                        continue

                    # Skip duplicates
                    if self.db.is_duplicate(shortcode):
                        continue

                    # Get video URL
                    video_url = str(media.video_url) if media.video_url else None

                    if not video_url:
                        continue

                    # Add to database
                    added = self.db.add_reel(
                        shortcode=shortcode,
                        source_account=username,
                        media_url=video_url,
                    )

                    if added:
                        reel_info = {
                            "shortcode": shortcode,
                            "source_account": username,
                            "video_url": video_url,
                            "caption": media.caption_text or "",
                        }
                        new_reels.append(reel_info)
                        logger.info(f"  ✅ New reel found: {shortcode} from @{username}")

            except UserNotFound:
                logger.error(f"  ❌ Profile @{username} not found, skipping.")
                continue
            except PleaseWaitFewMinutes:
                logger.warning(f"  ⏳ Rate limited while scanning @{username}. Skipping to next account.")
                time.sleep(10)  # Brief cooldown before trying next account
                continue
            except ClientError as e:
                logger.error(f"  ❌ API error for @{username}: {e}")
                continue
            except Exception as e:
                logger.error(f"  ❌ Error scanning @{username}: {e}")
                continue

        logger.info(f"📊 Scan complete. {len(new_reels)} new reel(s) discovered.")
        return new_reels
