"""
Main orchestrator — ties all modules together in an automated loop.

Usage:
    python main.py
"""

import os
import sys
import gc
import glob
import time
import asyncio
import logging
import signal
from datetime import datetime
from pathlib import Path

# Add project dir to path
sys.path.insert(0, os.path.dirname(__file__))

from config import Config
from database import Database
from scraper import ReelScraper
from downloader import ReelDownloader
from uploader import UploaderManager
from telegram_bot import TelegramNotifier

# ─── Logging Setup ───────────────────────────────────────────────────────────

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)-15s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(LOG_DIR, f"bot_{datetime.now().strftime('%Y%m%d')}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("main")

# ─── Globals ─────────────────────────────────────────────────────────────────

shutdown_flag = False


def handle_shutdown(signum, frame):
    global shutdown_flag
    logger.info("🛑 Shutdown signal received. Finishing current cycle...")
    shutdown_flag = True


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


# ─── Main Cycle ──────────────────────────────────────────────────────────────

async def run_cycle(
    config: Config,
    db: Database,
    scraper: ReelScraper,
    downloader: ReelDownloader,
    uploader_mgr: UploaderManager,
    telegram: TelegramNotifier,
):
    """Run one full scrape → download → upload cycle."""
    if telegram.paused:
        logger.info("⏸️ Bot is paused. Skipping cycle.")
        return

    logger.info("=" * 60)
    logger.info("🔄 Starting new cycle...")
    logger.info("=" * 60)

    discovered_count = 0
    downloaded_count = 0
    uploaded_count = 0

    # ── Step 1: Discover new reels ──
    try:
        new_reels = scraper.discover_reels(
            config.source_accounts,
            max_per_account=config.max_reels_per_cycle,
        )
        discovered_count = len(new_reels)
        await telegram.notify_scan_results(discovered_count, config.source_accounts)
    except Exception as e:
        logger.error(f"❌ Scraper error: {e}")
        await telegram.notify_error(f"Scraper failed: {e}")

    # ── Step 2: Download pending reels ──
    try:
        downloaded = downloader.download_pending(limit=config.max_reels_per_cycle)
        downloaded_count = len(downloaded)
        for reel in downloaded:
            await telegram.notify_download(reel["shortcode"], reel["source_account"], True)
    except Exception as e:
        logger.error(f"❌ Downloader error: {e}")
        await telegram.notify_error(f"Downloader failed: {e}")

    # ── Step 3: Upload pending reels (distributed across target accounts) ──
    try:
        uploaded = uploader_mgr.upload_pending(
            limit=config.max_reels_per_cycle,
            delay_minutes=config.upload_delay_minutes,
            batch_size=config.batch_size,
        )
        uploaded_count = len(uploaded)
        for reel in uploaded:
            target = reel.get("target_account", "unknown")
            await telegram.notify_upload(
                reel["shortcode"], reel["source_account"], True, target_account=target
            )
    except Exception as e:
        logger.error(f"❌ Uploader error: {e}")
        await telegram.notify_error(f"Uploader failed: {e}")

    # ── Summary ──
    await telegram.notify_cycle_summary(discovered_count, downloaded_count, uploaded_count)
    logger.info(f"✅ Cycle complete: {discovered_count} discovered, "
                f"{downloaded_count} downloaded, {uploaded_count} uploaded.")

    # ── Step 4: Cleanup worker ──
    await cleanup_worker(config, db, uploader_mgr, telegram)


# ─── Cleanup Worker ──────────────────────────────────────────────────────────

async def cleanup_worker(
    config: Config,
    db: Database,
    uploader_mgr: UploaderManager,
    telegram: TelegramNotifier,
):
    """
    Safety-net worker: scans the downloads folder and cleans up leftover files.
    - If a file's reel is already uploaded in DB → delete the file
    - If a file's reel is still 'downloaded' in DB → upload it via the first available uploader, then delete
    - If a file has no DB entry → delete it (orphan)
    """
    download_dir = config.download_dir
    if not os.path.exists(download_dir):
        return

    all_files = [
        os.path.join(download_dir, f)
        for f in os.listdir(download_dir)
        if os.path.isfile(os.path.join(download_dir, f))
    ]
    if not all_files:
        return

    logger.info(f"🧹 Cleanup worker: found {len(all_files)} file(s) in downloads/")
    cleaned = 0

    # Use first available uploader for cleanup uploads
    cleanup_uploader = uploader_mgr.uploaders[0] if uploader_mgr.uploaders else None

    for filepath in all_files:
        filename = os.path.basename(filepath)

        # Non-mp4 files (thumbnails like .mp4.jpg, etc.) — delete immediately
        if not filename.endswith(".mp4"):
            logger.info(f"  🗑️ Deleting non-video file: {filename}")
            _force_delete(filepath)
            cleaned += 1
            continue

        shortcode = filename.replace(".mp4", "")

        try:
            # Look up this reel in the database
            row = db.conn.execute(
                "SELECT status, source_account FROM reels WHERE shortcode = ?", (shortcode,)
            ).fetchone()

            if row is None:
                # Orphan file — no DB record, just delete
                logger.info(f"  🗑️ Orphan file (no DB entry): {filename}")
                _force_delete(filepath)
                cleaned += 1

            elif row["status"] == "uploaded":
                # Already uploaded — safe to delete
                logger.info(f"  🗑️ Already uploaded, deleting: {filename}")
                _force_delete(filepath)
                cleaned += 1

            elif row["status"] == "downloaded" and cleanup_uploader:
                # Not yet uploaded — upload it now, then delete
                logger.info(f"  📤 Missed upload, uploading now: {filename}")
                try:
                    source = row["source_account"] if row["source_account"] else "unknown"
                    caption = config.caption_template.replace("{source}", source)

                    media = cleanup_uploader.client.clip_upload(
                        Path(filepath), caption=caption
                    )
                    db.update_status(
                        shortcode, "uploaded",
                        target_account=cleanup_uploader.username
                    )
                    logger.info(f"  ✅ Uploaded {shortcode} (media ID: {media.pk})")
                    await telegram.notify_upload(
                        shortcode, source, True,
                        target_account=cleanup_uploader.username
                    )

                    # Now delete
                    _force_delete(filepath)
                    cleaned += 1
                except Exception as upload_err:
                    logger.error(f"  ❌ Cleanup upload failed for {shortcode}: {upload_err}")

            elif row["status"] == "failed":
                # Previously failed — just delete the file
                logger.info(f"  🗑️ Failed reel, deleting: {filename}")
                _force_delete(filepath)
                cleaned += 1

        except Exception as e:
            logger.error(f"  ❌ Cleanup error for {filename}: {e}")

    if cleaned > 0:
        logger.info(f"🧹 Cleanup done: {cleaned} file(s) removed.")
        await telegram.send_message(f"🧹 Cleanup worker removed <b>{cleaned}</b> leftover file(s).")


def _force_delete(filepath: str, retries: int = 3):
    """Force-delete a file with retries for Windows file locking."""
    for attempt in range(retries):
        try:
            gc.collect()
            time.sleep(1)
            if os.path.exists(filepath):
                os.remove(filepath)
            return
        except PermissionError:
            logger.warning(f"  ⏳ File locked, retry {attempt + 1}/{retries}...")
            time.sleep(3)
        except Exception:
            return
    logger.warning(f"  ⚠️ Could not delete {filepath} after {retries} retries")


# ─── Entry Point ─────────────────────────────────────────────────────────────

async def main():
    global shutdown_flag

    logger.info("🚀 Instagram Reel Bot starting up...")

    # Initialize
    config = Config()
    logger.info(f"📋 Config loaded: {config}")

    db = Database(config.db_path)
    downloader = ReelDownloader(db, config.download_dir)

    # Initialize multi-account uploader
    uploader_mgr = UploaderManager(
        db=db,
        target_accounts=config.target_accounts,
        caption_template=config.caption_template,
    )

    # Share authenticated client from first uploader with scraper
    scraper = ReelScraper(db, uploader_mgr.get_first_client())
    telegram = TelegramNotifier(
        config.telegram_bot_token, config.telegram_chat_id, db,
        target_accounts=uploader_mgr.get_account_names(),
    )

    # Start Telegram bot (polling in background)
    app = telegram.build_app()
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    await telegram.notify_startup()
    logger.info("✅ All modules initialized. Entering main loop...")

    try:
        while not shutdown_flag:
            await run_cycle(config, db, scraper, downloader, uploader_mgr, telegram)

            if shutdown_flag:
                break

            logger.info(
                f"💤 Sleeping for {config.check_interval_minutes} minutes "
                f"until next cycle..."
            )

            # Sleep in small increments so we can respond to shutdown
            for _ in range(config.check_interval_minutes * 60):
                if shutdown_flag:
                    break
                await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("🛑 KeyboardInterrupt received.")
    finally:
        logger.info("🧹 Shutting down gracefully...")
        await telegram.send_message("🛑 <b>Bot shutting down.</b>")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        db.close()
        logger.info("👋 Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
