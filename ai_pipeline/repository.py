"""SQLite persistence for structured campus announcements."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_pipeline.schema import AnnouncementDigest


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent.parent / "campussignal.db"
)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def to_utc_iso(value: datetime) -> str:
    """Normalize a datetime to an ISO-8601 UTC timestamp."""
    if value.tzinfo is None:
        raise ValueError("Timestamp must include timezone information.")

    return value.astimezone(timezone.utc).isoformat()


class AnnouncementRepository:
    """Store and expire structured announcements in SQLite."""

    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = str(db_path)

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10)

    def initialize(self):
        """Create the structured-announcements table if needed."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS structured_announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    normalized TEXT NOT NULL UNIQUE,
                    announcement_type TEXT NOT NULL,
                    summary_title TEXT NOT NULL,
                    required_action TEXT NOT NULL,
                    date_or_deadline TEXT NOT NULL,
                    urgency_level TEXT NOT NULL,
                    ranking_reason TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'dashboard',
                    channel_id TEXT,
                    slack_ts TEXT,
                    received_at TEXT NOT NULL,
                    deadline_at TEXT,
                    expires_at TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_structured_announcements_expires_at
                ON structured_announcements(expires_at)
            """)

    def save(
        self,
        message: str,
        digest: AnnouncementDigest,
        *,
        received_at: datetime | None = None,
        deadline_at: datetime | None = None,
        source: str = "dashboard",
        channel_id: str | None = None,
        slack_ts: str | None = None,
    ) -> tuple[bool, int | None]:
        """
        Save a validated digest.

        deadline_at must be a resolved absolute datetime. Relative or
        ambiguous deadlines must not be passed here as guessed values.
        """
        if not message or not message.strip():
            raise ValueError("Message cannot be empty.")

        received_at = received_at or utc_now()

        if received_at.tzinfo is None:
            raise ValueError("received_at must include timezone information.")

        if deadline_at is not None and deadline_at.tzinfo is None:
            raise ValueError("deadline_at must include timezone information.")

        received_iso = to_utc_iso(received_at)
        deadline_iso = (
            to_utc_iso(deadline_at) if deadline_at is not None else None
        )
        expires_iso = (
            to_utc_iso(
                deadline_at.astimezone(timezone.utc)
                + timedelta(hours=24)
            )
            if deadline_at is not None
            else None
        )

        normalized = " ".join(message.strip().lower().split())
        data = digest.model_dump()

        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO structured_announcements (
                    message, normalized, announcement_type,
                    summary_title, required_action, date_or_deadline,
                    urgency_level, ranking_reason, confidence_score,
                    source_url, source, channel_id, slack_ts,
                    received_at, deadline_at, expires_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message.strip(),
                normalized,
                data["announcement_type"],
                data["summary_title"],
                data["required_action"],
                data["date_or_deadline"],
                data["urgency_level"],
                data["ranking_reason"],
                data["confidence_score"],
                data["source_url"],
                source,
                channel_id,
                slack_ts,
                received_iso,
                deadline_iso,
                expires_iso,
                to_utc_iso(utc_now()),
            ))

            if cursor.rowcount == 0:
                existing = conn.execute(
                    "SELECT id FROM structured_announcements "
                    "WHERE normalized = ?",
                    (normalized,),
                ).fetchone()
                return False, existing[0] if existing else None

            return True, cursor.lastrowid

    def delete_expired(
        self,
        now: datetime | None = None,
    ) -> int:
        """Delete announcements whose deadline plus 24 hours has passed."""
        now = now or utc_now()
        now_iso = to_utc_iso(now)

        with self._connect() as conn:
            cursor = conn.execute("""
                DELETE FROM structured_announcements
                WHERE expires_at IS NOT NULL
                  AND expires_at <= ?
            """, (now_iso,))
            return cursor.rowcount

    def list_active(self, now: datetime | None = None):
        """Return announcements whose expiry time has not passed."""
        now = now or utc_now()
        now_iso = to_utc_iso(now)

        with self._connect() as conn:
            return conn.execute("""
                SELECT id, message, announcement_type, summary_title,
                       required_action, date_or_deadline, urgency_level,
                       ranking_reason, confidence_score, source_url,
                       source, channel_id, received_at, deadline_at,
                       expires_at
                FROM structured_announcements
                WHERE expires_at IS NULL OR expires_at > ?
                ORDER BY
                    CASE urgency_level
                        WHEN 'HIGH' THEN 1
                        WHEN 'MEDIUM' THEN 2
                        ELSE 3
                    END,
                    received_at DESC
            """, (now_iso,)).fetchall()
