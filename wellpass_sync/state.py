from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import BookingEvent, SourceEmail


class SyncState:
    def __init__(self, database_path: str | Path, writable: bool = True) -> None:
        self.path = Path(database_path)
        self.writable = writable
        if writable:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.path)
        elif self.path.exists():
            db_uri = self.path.resolve().as_uri() + "?mode=ro"
            self.connection = sqlite3.connect(db_uri, uri=True)
        else:
            self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        if writable or not self.path.exists():
            self._init_schema()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SyncState":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def has_processed_message(self, source: SourceEmail) -> bool:
        row = self.connection.execute(
            "SELECT content_hash FROM messages WHERE message_id = ?",
            (source.message_id,),
        ).fetchone()
        return bool(row and row["content_hash"] == content_hash(source.raw_bytes))

    def record_message(self, source: SourceEmail, event: BookingEvent | None, action: str) -> None:
        self._require_writable()
        now = _now()
        self.connection.execute(
            """
            INSERT INTO messages (
                message_id, content_hash, subject, sender, sent_at, fingerprint,
                status, calendar_uid, action, processed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                content_hash = excluded.content_hash,
                subject = excluded.subject,
                sender = excluded.sender,
                sent_at = excluded.sent_at,
                fingerprint = excluded.fingerprint,
                status = excluded.status,
                calendar_uid = excluded.calendar_uid,
                action = excluded.action,
                processed_at = excluded.processed_at
            """,
            (
                source.message_id,
                content_hash(source.raw_bytes),
                source.subject,
                source.sender,
                _iso(source.sent_at),
                event.fingerprint if event else None,
                event.status if event else "ignored",
                event.calendar_uid if event else None,
                action,
                now,
            ),
        )
        self.connection.commit()

    def get_booking(self, fingerprint: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM bookings WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()

    def find_booking_for_cancellation(self, event: BookingEvent) -> sqlite3.Row | None:
        if event.booking_id:
            row = self.connection.execute(
                """
                SELECT * FROM bookings
                WHERE booking_id = ? AND status != 'cancelled'
                ORDER BY start_at DESC
                LIMIT 1
                """,
                (event.booking_id,),
            ).fetchone()
            if row:
                return row

        row = self.get_booking(event.fingerprint)
        if row and row["status"] != "cancelled":
            return row

        if event.title:
            return self.connection.execute(
                """
                SELECT * FROM bookings
                WHERE lower(title) = lower(?)
                  AND COALESCE(lower(studio), '') = COALESCE(lower(?), '')
                  AND status != 'cancelled'
                ORDER BY start_at DESC
                LIMIT 1
                """,
                (event.title, event.studio),
            ).fetchone()
        return None

    def upsert_booking(self, event: BookingEvent, calendar_href: str | None = None) -> None:
        self._require_writable()
        if not event.start_at or not event.end_at:
            raise ValueError("Cannot upsert booking without start/end datetimes")
        now = _now()
        event_hash = event_content_hash(event)
        self.connection.execute(
            """
            INSERT INTO bookings (
                fingerprint, booking_id, title, studio, start_at, end_at, timezone,
                location, status, calendar_uid, calendar_href, last_message_id,
                content_hash, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                booking_id = excluded.booking_id,
                title = excluded.title,
                studio = excluded.studio,
                start_at = excluded.start_at,
                end_at = excluded.end_at,
                timezone = excluded.timezone,
                location = excluded.location,
                status = excluded.status,
                calendar_uid = excluded.calendar_uid,
                calendar_href = COALESCE(excluded.calendar_href, bookings.calendar_href),
                last_message_id = excluded.last_message_id,
                content_hash = excluded.content_hash,
                updated_at = excluded.updated_at
            """,
            (
                event.fingerprint,
                event.booking_id,
                event.title,
                event.studio,
                _iso(event.start_at),
                _iso(event.end_at),
                event.timezone,
                event.location,
                event.status,
                event.calendar_uid,
                calendar_href,
                event.source_message_id,
                event_hash,
                now,
            ),
        )
        self.connection.commit()

    def mark_booking_cancelled(self, fingerprint: str, message_id: str) -> None:
        self._require_writable()
        self.connection.execute(
            """
            UPDATE bookings
            SET status = 'cancelled', last_message_id = ?, updated_at = ?
            WHERE fingerprint = ?
            """,
            (message_id, _now(), fingerprint),
        )
        self.connection.commit()

    def event_changed(self, row: sqlite3.Row | None, event: BookingEvent) -> bool:
        if not row:
            return True
        return row["content_hash"] != event_content_hash(event) or row["status"] != event.status

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                subject TEXT,
                sender TEXT,
                sent_at TEXT,
                fingerprint TEXT,
                status TEXT,
                calendar_uid TEXT,
                action TEXT,
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookings (
                fingerprint TEXT PRIMARY KEY,
                booking_id TEXT,
                title TEXT NOT NULL,
                studio TEXT,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                timezone TEXT NOT NULL,
                location TEXT,
                status TEXT NOT NULL,
                calendar_uid TEXT NOT NULL,
                calendar_href TEXT,
                last_message_id TEXT,
                content_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_bookings_booking_id ON bookings(booking_id);
            CREATE INDEX IF NOT EXISTS idx_messages_fingerprint ON messages(fingerprint);
            """
        )
        self.connection.commit()

    def _require_writable(self) -> None:
        if not self.writable:
            raise RuntimeError("SyncState was opened read-only")


def content_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def event_content_hash(event: BookingEvent) -> str:
    values: dict[str, Any] = asdict(event)
    for key in ("source_message_id", "source_subject", "source_sender", "notes"):
        values.pop(key, None)
    normalized = "|".join(f"{key}={values[key]}" for key in sorted(values))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
