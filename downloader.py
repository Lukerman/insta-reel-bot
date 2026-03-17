"""
Reel downloader — downloads reel video files from discovered URLs.
"""

import os
import logging
import requests

from database import Database

logger = logging.getLogger(__name__)


class ReelDownloader:
    """Downloads reel videos to a local directory."""

    def __init__(self, db: Database, download_dir: str):
        self.db = db
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)

    def download_pending(self, limit: int = 10) -> list[dict]:
        """
        Download all pending reels (status='discovered').
        Returns list of successfully downloaded reel dicts.
        """
        pending = self.db.get_pending_downloads(limit=limit)
        downloaded = []

        for reel in pending:
            shortcode = reel["shortcode"]
            video_url = reel["media_url"]

            if not video_url:
                logger.warning(f"⚠️ No video URL for {shortcode}, skipping.")
                self.db.update_status(shortcode, "failed", error_message="No video URL")
                continue

            try:
                logger.info(f"⬇️ Downloading reel {shortcode}...")
                local_path = self._download_video(shortcode, video_url)

                self.db.update_status(shortcode, "downloaded", local_path=local_path)
                reel["local_path"] = local_path
                downloaded.append(reel)
                logger.info(f"  ✅ Downloaded: {local_path}")

            except Exception as e:
                logger.error(f"  ❌ Failed to download {shortcode}: {e}")
                self.db.update_status(shortcode, "failed", error_message=str(e))

        logger.info(f"📦 Download complete. {len(downloaded)}/{len(pending)} successful.")
        return downloaded

    def _download_video(self, shortcode: str, url: str) -> str:
        """Download a video file from URL and return the local path."""
        filename = f"{shortcode}.mp4"
        local_path = os.path.join(self.download_dir, filename)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Validate file size (at least 10KB)
        file_size = os.path.getsize(local_path)
        if file_size < 10240:
            os.remove(local_path)
            raise ValueError(f"Downloaded file too small ({file_size} bytes), likely invalid")

        return local_path

    def cleanup_file(self, local_path: str):
        """Remove a downloaded file after successful upload."""
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
                logger.info(f"🗑️ Cleaned up: {local_path}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to cleanup {local_path}: {e}")
