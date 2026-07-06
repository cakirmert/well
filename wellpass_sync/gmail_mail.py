from __future__ import annotations

import base64
from datetime import datetime, timezone

from .config import AppConfig
from .google_auth import GMAIL_READ_SCOPE, build_google_service
from .models import SourceEmail
from .parser import source_email_from_bytes


def load_gmail_emails(
    config: AppConfig,
    sender_contains: str | None = None,
    max_messages: int | None = None,
) -> list[SourceEmail]:
    service = build_google_service(config, "gmail", "v1", [GMAIL_READ_SCOPE])
    max_count = max_messages or (config.imap_max_messages if config.imap_max_messages > 0 else 100)
    query = _gmail_query(config, sender_contains)
    print(f"Gmail: fetching up to {max_count} message(s) matching {query!r}", flush=True)

    messages: list[SourceEmail] = []
    page_token = None
    while len(messages) < max_count:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=min(100, max_count - len(messages)),
                pageToken=page_token,
            )
            .execute()
        )
        for item in response.get("messages", []):
            source = _load_raw_message(service, item["id"])
            if _matches_since(source, config.search_since_days):
                messages.append(source)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    print(f"Gmail: loaded {len(messages)} matching message(s).", flush=True)
    return messages


def _load_raw_message(service, message_id: str) -> SourceEmail:
    payload = service.users().messages().get(userId="me", id=message_id, format="raw").execute()
    raw = payload.get("raw") or ""
    raw_bytes = base64.urlsafe_b64decode(_pad_base64(raw))
    return source_email_from_bytes(raw_bytes)


def _gmail_query(config: AppConfig, sender_contains: str | None) -> str:
    parts = [f"newer_than:{max(1, config.search_since_days)}d"]
    sender = sender_contains or (config.email_sender_hints[0] if config.email_sender_hints else "")
    if sender:
        if "@" in sender:
            parts.append(f"from:{sender}")
        else:
            parts.append(sender)
    elif config.email_body_hints:
        parts.append(config.email_body_hints[0])
    return " ".join(parts)


def _pad_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return (value + padding).encode("ascii")


def _matches_since(source: SourceEmail, since_days: int) -> bool:
    if not source.sent_at:
        return True
    cutoff = datetime.now(timezone.utc).timestamp() - since_days * 24 * 60 * 60
    return source.sent_at.timestamp() >= cutoff
