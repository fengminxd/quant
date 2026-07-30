"""Persistent Telegram event de-duplication."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from notifications.models import NotificationMatch


@dataclass(frozen=True)
class PendingNotification:
    """One durable Telegram payload awaiting successful delivery."""

    identity: str
    symbol: str
    timeframe: str
    pattern_id: str
    rule: str
    detected_timestamp: str
    filename: str
    caption: str
    image: bytes


class NotificationEventStore:
    """Remember successfully delivered event identities across restarts."""

    def __init__(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(target)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_notifications (
                identity TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                pattern_id TEXT NOT NULL,
                rule TEXT NOT NULL,
                detected_timestamp TEXT NOT NULL,
                sent_at TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_outbox (
                identity TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                pattern_id TEXT NOT NULL,
                rule TEXT NOT NULL,
                detected_timestamp TEXT NOT NULL,
                filename TEXT NOT NULL,
                caption TEXT NOT NULL,
                image BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_scan_cursors (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                last_open_time INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (symbol, timeframe)
            )
            """
        )
        self.connection.commit()

    def contains(self, identity: str) -> bool:
        """Return whether this exact Pattern/anchor event was already delivered."""

        row = self.connection.execute(
            """
            SELECT 1 FROM sent_notifications WHERE identity = ?
            UNION ALL
            SELECT 1 FROM notification_outbox WHERE identity = ?
            LIMIT 1
            """,
            (identity, identity),
        ).fetchone()
        return row is not None

    def enqueue(
        self,
        match: NotificationMatch,
        *,
        filename: str,
        caption: str,
        image: bytes,
    ) -> None:
        """Persist a Telegram payload before attempting network delivery."""

        self.connection.execute(
            """
            INSERT OR IGNORE INTO notification_outbox (
                identity, symbol, timeframe, pattern_id, rule,
                detected_timestamp, filename, caption, image, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match.identity,
                match.symbol,
                match.timeframe,
                match.pattern.pattern_id,
                match.rule,
                str(match.detected_timestamp),
                filename,
                caption,
                image,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.connection.commit()

    def pending(self) -> list[PendingNotification]:
        """Return durable unsent payloads in creation order."""

        rows = self.connection.execute(
            """
            SELECT identity, symbol, timeframe, pattern_id, rule,
                   detected_timestamp, filename, caption, image
            FROM notification_outbox
            ORDER BY created_at, identity
            """
        ).fetchall()
        return [PendingNotification(*row) for row in rows]

    def pending_count(self) -> int:
        """Return the number of durable payloads awaiting Telegram."""

        row = self.connection.execute(
            "SELECT COUNT(*) FROM notification_outbox"
        ).fetchone()
        return int(row[0]) if row else 0

    def last_scanned_open_time(self, symbol: str, timeframe: str) -> int | None:
        """Return the durable right edge last scanned for one stream."""

        row = self.connection.execute(
            """
            SELECT last_open_time
            FROM notification_scan_cursors
            WHERE symbol = ? AND timeframe = ?
            """,
            (symbol, timeframe),
        ).fetchone()
        return int(row[0]) if row else None

    def mark_scanned(self, symbol: str, timeframe: str, open_time: int) -> None:
        """Advance a stream cursor only after its Pattern scan completes."""

        self.connection.execute(
            """
            INSERT INTO notification_scan_cursors (
                symbol, timeframe, last_open_time, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe) DO UPDATE SET
                last_open_time = excluded.last_open_time,
                updated_at = excluded.updated_at
            WHERE excluded.last_open_time > notification_scan_cursors.last_open_time
            """,
            (
                symbol,
                timeframe,
                open_time,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.connection.commit()

    def mark_pending_sent(self, item: PendingNotification) -> None:
        """Atomically move one delivered payload from outbox to sent history."""

        with self.connection:
            self.connection.execute(
                """
                INSERT OR IGNORE INTO sent_notifications (
                    identity, symbol, timeframe, pattern_id, rule,
                    detected_timestamp, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.identity,
                    item.symbol,
                    item.timeframe,
                    item.pattern_id,
                    item.rule,
                    item.detected_timestamp,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self.connection.execute(
                "DELETE FROM notification_outbox WHERE identity = ?",
                (item.identity,),
            )

    def mark_sent(self, match: NotificationMatch) -> None:
        """Persist one successfully delivered notification."""

        self.connection.execute(
            """
            INSERT OR IGNORE INTO sent_notifications (
                identity, symbol, timeframe, pattern_id, rule,
                detected_timestamp, sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match.identity,
                match.symbol,
                match.timeframe,
                match.pattern.pattern_id,
                match.rule,
                str(match.detected_timestamp),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
