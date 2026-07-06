from __future__ import annotations

import imaplib
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

from .config import AppConfig
from .models import SourceEmail
from .parser import source_email_from_bytes


def load_sample_emails(directory: str | Path) -> list[SourceEmail]:
    path = Path(directory)
    messages: list[SourceEmail] = []
    if not path.exists():
        return messages
    for eml_path in sorted(path.glob("*.eml")):
        messages.append(source_email_from_bytes(eml_path.read_bytes()))
    return messages


def load_imap_emails(config: AppConfig) -> list[SourceEmail]:
    config.validate_imap()
    since = datetime.now() - timedelta(days=config.search_since_days)
    since_arg = since.strftime("%d-%b-%Y")
    messages: list[SourceEmail] = []

    with imaplib.IMAP4_SSL(config.imap_host, config.imap_port) as mailbox:
        mailbox.login(config.imap_username, config.imap_password)
        mailbox.select(config.imap_folder)
        status, data = mailbox.search(None, "SINCE", since_arg)
        if status != "OK":
            raise RuntimeError(f"IMAP search failed with status {status!r}")

        ids = data[0].split()
        if config.imap_max_messages > 0:
            ids = ids[-config.imap_max_messages :]

        for message_id in ids:
            status, fetch_data = mailbox.fetch(message_id, "(RFC822)")
            if status != "OK":
                continue
            for item in fetch_data:
                if not isinstance(item, tuple):
                    continue
                source = source_email_from_bytes(item[1])
                if _matches_hints(source, config):
                    messages.append(source)
                break
    return messages


def load_outlook_com_emails(config: AppConfig) -> list[SourceEmail]:
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError(
            "Reading the signed-in Outlook app requires pywin32. "
            "Install dependencies with: .\\.venv\\Scripts\\python.exe -m pip install -e ."
        ) from exc

    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    folder = outlook.GetDefaultFolder(6)  # olFolderInbox
    items = folder.Items
    items.Sort("[ReceivedTime]", True)

    since = datetime.now() - timedelta(days=config.search_since_days)
    messages: list[SourceEmail] = []
    max_messages = config.imap_max_messages if config.imap_max_messages > 0 else 500

    for index in range(1, min(items.Count, max_messages) + 1):
        item = items.Item(index)
        if getattr(item, "Class", None) != 43:  # olMail
            continue

        sent_at = _com_datetime(getattr(item, "SentOn", None)) or _com_datetime(
            getattr(item, "ReceivedTime", None)
        )
        if sent_at and sent_at.replace(tzinfo=None) < since:
            break

        subject = str(getattr(item, "Subject", "") or "")
        sender = _outlook_sender(item)
        body = str(getattr(item, "Body", "") or getattr(item, "HTMLBody", "") or "")
        message_id = _outlook_message_id(item)
        raw_bytes = "\n".join(
            [
                f"Message-ID: {message_id}",
                f"From: {sender}",
                f"Subject: {subject}",
                f"Date: {sent_at.isoformat() if sent_at else ''}",
                "",
                body,
            ]
        ).encode("utf-8", errors="replace")

        source = SourceEmail(
            message_id=message_id,
            subject=subject,
            sender=sender,
            sent_at=sent_at,
            body_text=body,
            raw_bytes=raw_bytes,
        )
        if _matches_hints(source, config):
            messages.append(source)

    return messages


def _matches_hints(source: SourceEmail, config: AppConfig) -> bool:
    sender = source.sender.lower()
    subject = source.subject.lower()
    body = source.body_text.lower()

    has_any_hint = bool(config.email_sender_hints or config.email_subject_hints or config.email_body_hints)
    if not has_any_hint:
        return True

    if any(hint in sender for hint in config.email_sender_hints):
        return True
    if any(hint in subject for hint in config.email_subject_hints):
        return True
    if any(hint in body for hint in config.email_body_hints):
        return True
    return False


def _outlook_sender(item) -> str:
    name = str(getattr(item, "SenderName", "") or "")
    address = str(getattr(item, "SenderEmailAddress", "") or "")
    try:
        sender = item.Sender
        if sender is not None:
            exchange_user = sender.GetExchangeUser()
            if exchange_user is not None and exchange_user.PrimarySmtpAddress:
                address = str(exchange_user.PrimarySmtpAddress)
    except Exception:
        pass
    if name and address:
        return f"{name} <{address}>"
    return address or name


def _outlook_message_id(item) -> str:
    try:
        value = item.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x1035001F")
        if value:
            return str(value)
    except Exception:
        pass
    entry_id = str(getattr(item, "EntryID", "") or "")
    return entry_id or f"outlook-missing-id-{abs(hash(str(getattr(item, 'Subject', ''))))}"


def _com_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromtimestamp(value.timestamp())
    except Exception:
        return None


def sorted_messages(messages: Iterable[SourceEmail]) -> list[SourceEmail]:
    def key(message: SourceEmail):
        if message.sent_at:
            try:
                return message.sent_at.timestamp()
            except (OverflowError, OSError):
                pass
        try:
            parsed = parsedate_to_datetime(message.subject)
            return parsed.timestamp()
        except Exception:
            return 0

    return sorted(messages, key=key)
