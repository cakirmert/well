from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class SourceEmail:
    message_id: str
    subject: str
    sender: str
    sent_at: datetime | None
    body_text: str
    raw_bytes: bytes
    attachments: tuple[EmailAttachment, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BookingEvent:
    source_message_id: str
    source_subject: str
    source_sender: str
    booking_id: str | None
    title: str
    studio: str | None
    start_at: datetime | None
    end_at: datetime | None
    timezone: str
    location: str | None
    status: str
    fingerprint: str
    calendar_uid: str
    notes: str

    @property
    def is_cancelled(self) -> bool:
        return self.status == "cancelled"
