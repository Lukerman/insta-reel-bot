"""
SQLite database manager for tracking reel lifecycle.
States: discovered → downloaded → uploaded (or failed at any step).
"""

import sqlite3
from datetime import datetime


class Database:
    """Manages the reels tracking database."""

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shortcode TEXT UNIQUE NOT NULL,
                source_account TEXT NOT NULL,
                media_url TEXT,
                status TEXT NOT NULL DEFAULT 'discovered',
                local_path TEXT,
                error_message TEXT,
                discovered_at TEXT NOT NULL,
                downloaded_at TEXT,
                uploaded_at TEXT
            )
        """)
        self.conn.commit()

    def is_duplicate(self, shortcode: str) -> bool:
        """Check if a reel with this shortcode already exists."""
        row = self.conn.execute(
            "SELECT 1 FROM reels WHERE shortcode = ?", (shortcode,)
        ).fetchone()
        return row is not None

    def add_reel(self, shortcode: str, source_account: str, media_url: str = None) -> bool:
        """Add a newly discovered reel. Returns True if added, False if duplicate."""
        if self.is_duplicate(shortcode):
            return False
        self.conn.execute(
            """INSERT INTO reels (shortcode, source_account, media_url, status, discovered_at)
               VALUES (?, ?, ?, 'discovered', ?)""",
            (shortcode, source_account, media_url, datetime.now().isoformat())
        )
        self.conn.commit()
        return True

    def update_status(self, shortcode: str, status: str, **kwargs):
        """
        Update a reel's status and optional fields.
        Supported kwargs: local_path, error_message
        """
        sets = ["status = ?"]
        params = [status]

        if status == "downloaded":
            sets.append("downloaded_at = ?")
            params.append(datetime.now().isoformat())
        elif status == "uploaded":
            sets.append("uploaded_at = ?")
            params.append(datetime.now().isoformat())

        if "local_path" in kwargs:
            sets.append("local_path = ?")
            params.append(kwargs["local_path"])
        if "error_message" in kwargs:
            sets.append("error_message = ?")
            params.append(kwargs["error_message"])

        params.append(shortcode)
        self.conn.execute(
            f"UPDATE reels SET {', '.join(sets)} WHERE shortcode = ?", params
        )
        self.conn.commit()

    def get_pending_downloads(self, limit: int = 10) -> list:
        """Get reels that are discovered but not yet downloaded."""
        rows = self.conn.execute(
            "SELECT * FROM reels WHERE status = 'discovered' ORDER BY discovered_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_uploads(self, limit: int = 10) -> list:
        """Get reels that are downloaded but not yet uploaded."""
        rows = self.conn.execute(
            "SELECT * FROM reels WHERE status = 'downloaded' ORDER BY downloaded_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get counts of reels by status."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as count FROM reels GROUP BY status"
        ).fetchall()
        stats = {row["status"]: row["count"] for row in rows}
        total = sum(stats.values())
        stats["total"] = total
        return stats

    def get_recent(self, limit: int = 5) -> list:
        """Get the most recently updated reels."""
        rows = self.conn.execute(
            """SELECT shortcode, source_account, status, 
                      COALESCE(uploaded_at, downloaded_at, discovered_at) as last_update
               FROM reels ORDER BY last_update DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
