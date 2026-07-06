from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .models import BookingEvent, EmailAttachment, SourceEmail


GERMAN_MONTHS = {
    "januar": 1,
    "jan": 1,
    "februar": 2,
    "feb": 2,
    "maerz": 3,
    "marz": 3,
    "maer": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "oktober": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "dez": 12,
}

ENGLISH_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

CANCEL_WORDS = (
    "cancelled",
    "canceled",
    "cancellation",
    "cancelation",
    "storniert",
    "stornierung",
    "abgesagt",
    "abmeldung",
)

LABELS = {
    "booking_id": (
        "booking id",
        "booking-id",
        "reservation id",
        "reservierungsnummer",
        "buchungsnummer",
        "buchungscode",
        "buchungs-id",
    ),
    "title": ("booked", "class", "course", "event", "workout", "training", "kurs", "termin"),
    "studio": ("studio", "provider", "partner", "club", "anbieter"),
    "location": ("location", "address", "adresse", "ort"),
}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "p", "div", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return html.unescape("".join(self.parts))


def source_email_from_bytes(raw_bytes: bytes) -> SourceEmail:
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    body = _message_body_text(msg)
    subject = str(msg.get("Subject", "")).strip()
    sender = str(msg.get("From", "")).strip()
    message_id = str(msg.get("Message-ID", "")).strip()
    if not message_id:
        message_id = f"missing-message-id-{hashlib.sha256(raw_bytes).hexdigest()[:16]}"

    sent_at = None
    if msg.get("Date"):
        try:
            sent_at = parsedate_to_datetime(str(msg.get("Date")))
        except (TypeError, ValueError):
            sent_at = None

    return SourceEmail(
        message_id=message_id,
        subject=subject,
        sender=sender,
        sent_at=sent_at,
        body_text=body,
        raw_bytes=raw_bytes,
        attachments=tuple(_message_attachments(msg)),
    )


def parse_booking_email(source: SourceEmail, default_timezone: str = "Europe/Berlin") -> BookingEvent | None:
    text = _normalize_text(f"{source.subject}\n{source.body_text}")
    lines = _meaningful_lines(text)
    lowered = text.lower()
    if "missed session" in lowered or "no-show notice" in lowered:
        return None

    is_cancelled = any(word in lowered for word in CANCEL_WORDS)

    fields = _extract_labeled_fields(lines)
    wellpass_fields = _extract_wellpass_fields(lines, source.subject)
    for key, value in wellpass_fields.items():
        fields.setdefault(key, value)
    booking_id = fields.get("booking_id")
    ics_event = _parse_ics_attachment(source.attachments, default_timezone)

    title, subject_studio = _infer_title_and_studio(source.subject)
    title = fields.get("title") or (ics_event["title"] if ics_event else None) or title
    studio = fields.get("studio") or _find_wellpass_studio(lines) or subject_studio or _sender_display_name(source.sender)
    location = (ics_event["location"] if ics_event else None) or fields.get("location")

    date_value = _find_date(text)
    time_range = _find_time_range(lines)
    start_at = ics_event["start_at"] if ics_event else None
    end_at = ics_event["end_at"] if ics_event else None
    tz = ZoneInfo(default_timezone)
    if not start_at and date_value and time_range:
        start_time, end_time = time_range
        start_at = datetime.combine(date_value, start_time, tzinfo=tz)
        end_at = datetime.combine(date_value, end_time, tzinfo=tz)
        if end_at <= start_at:
            end_at = end_at + timedelta(days=1)
    elif not start_at and date_value:
        single_time = _find_single_time(lines)
        if single_time:
            duration = _find_duration_minutes(text) or 60
            start_at = datetime.combine(date_value, single_time, tzinfo=tz)
            end_at = start_at + timedelta(minutes=duration)
    elif start_at and not end_at:
        duration = _find_duration_minutes(text) or 60
        end_at = start_at + timedelta(minutes=duration)

    if not title and not booking_id:
        return None
    if not is_cancelled and not start_at:
        return None

    title = title or "Wellpass booking"
    fingerprint = _fingerprint(booking_id, title, studio, start_at)
    calendar_uid = f"wellpass-{fingerprint}@local"
    status = "cancelled" if is_cancelled or (ics_event and ics_event["status"] == "cancelled") else "confirmed"
    notes = _build_notes(source, booking_id, studio, fields)

    return BookingEvent(
        source_message_id=source.message_id,
        source_subject=source.subject,
        source_sender=source.sender,
        booking_id=booking_id,
        title=title,
        studio=studio,
        start_at=start_at,
        end_at=end_at,
        timezone=default_timezone,
        location=location,
        status=status,
        fingerprint=fingerprint,
        calendar_uid=calendar_uid,
        notes=notes,
    )


def _message_body_text(msg: EmailMessage) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            try:
                content = part.get_content()
            except Exception:
                continue
            if content_type == "text/plain":
                plain_parts.append(str(content))
            elif content_type == "text/html":
                html_parts.append(_html_to_text(str(content)))
    else:
        try:
            content = msg.get_content()
        except Exception:
            content = ""
        if msg.get_content_type() == "text/html":
            html_parts.append(_html_to_text(str(content)))
        else:
            plain_parts.append(str(content))

    return "\n".join(plain_parts or html_parts)


def _message_attachments(msg: EmailMessage) -> list[EmailAttachment]:
    attachments: list[EmailAttachment] = []
    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        filename = part.get_filename() or ""
        content_type = part.get_content_type() or ""
        disposition = part.get_content_disposition()
        is_calendar = content_type == "text/calendar" or filename.lower().endswith(".ics")
        if disposition != "attachment" and not is_calendar:
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            try:
                payload = str(part.get_content()).encode("utf-8", errors="replace")
            except Exception:
                payload = b""
        attachments.append(
            EmailAttachment(
                filename=filename,
                content_type=content_type,
                content=payload,
            )
        )
    return attachments


def _html_to_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    return parser.text()


def _normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _meaningful_lines(text: str) -> list[str]:
    return [line.strip(" -\t") for line in text.splitlines() if line.strip(" -\t")]


def _extract_labeled_fields(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    label_lookup = {label: key for key, labels in LABELS.items() for label in labels}
    labels_pattern = "|".join(re.escape(label) for label in sorted(label_lookup, key=len, reverse=True))
    pattern = re.compile(rf"^\s*({labels_pattern})\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE)

    for line in lines:
        match = pattern.match(line)
        if not match:
            continue
        key = label_lookup[match.group(1).lower()]
        value = _clean_value(match.group(2))
        if value and key not in found:
            found[key] = value
    return found


def _parse_ics_attachment(
    attachments: tuple[EmailAttachment, ...],
    default_timezone: str,
) -> dict[str, object] | None:
    for attachment in attachments:
        name = attachment.filename.lower()
        content_type = attachment.content_type.lower()
        if content_type != "text/calendar" and not name.endswith(".ics"):
            continue
        try:
            text = attachment.content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = attachment.content.decode("latin-1", errors="replace")
        properties = _parse_ics_properties(text, default_timezone)
        if properties:
            return properties
    return None


def _parse_ics_properties(text: str, default_timezone: str) -> dict[str, object] | None:
    lines = _unfold_ics_lines(text)
    in_event = False
    values: dict[str, object] = {}
    method = ""
    for line in lines:
        if line.upper() == "BEGIN:VEVENT":
            in_event = True
            continue
        if line.upper() == "END:VEVENT":
            break
        if not in_event:
            if line.upper().startswith("METHOD:"):
                method = line.split(":", 1)[1].strip().lower()
            continue
        if ":" not in line:
            continue
        name_params, value = line.split(":", 1)
        name, params = _parse_ics_name_params(name_params)
        value = _unescape_ics_value(value.strip())
        if name == "UID":
            values["uid"] = value
        elif name == "SUMMARY":
            values["title"] = _clean_value(value)
        elif name == "LOCATION":
            values["location"] = _clean_value(value)
        elif name == "DESCRIPTION":
            values["description"] = value
        elif name == "STATUS":
            values["status"] = "cancelled" if value.lower() == "cancelled" else "confirmed"
        elif name == "DTSTART":
            values["start_at"] = _parse_ics_datetime(value, params.get("TZID"), default_timezone)
        elif name == "DTEND":
            values["end_at"] = _parse_ics_datetime(value, params.get("TZID"), default_timezone)

    if method == "cancel":
        values["status"] = "cancelled"
    values.setdefault("status", "confirmed")
    if not values.get("start_at") and not values.get("title"):
        return None
    return values


def _unfold_ics_lines(text: str) -> list[str]:
    unfolded: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw_line[1:]
        elif raw_line:
            unfolded.append(raw_line)
    return unfolded


def _parse_ics_name_params(value: str) -> tuple[str, dict[str, str]]:
    parts = value.split(";")
    name = parts[0].upper()
    params: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, param_value = part.split("=", 1)
        params[key.upper()] = param_value.strip('"')
    return name, params


def _parse_ics_datetime(value: str, tzid: str | None, default_timezone: str) -> datetime | None:
    tz = ZoneInfo(tzid or default_timezone)
    formats = ["%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"]
    is_utc = value.endswith("Z")
    clean_value = value[:-1] if is_utc else value
    for fmt in formats:
        try:
            parsed = datetime.strptime(clean_value, fmt)
            if fmt == "%Y%m%d":
                parsed = parsed.replace(hour=0, minute=0)
            if is_utc:
                return parsed.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(default_timezone))
            return parsed.replace(tzinfo=tz).astimezone(ZoneInfo(default_timezone))
        except ValueError:
            continue
    return None


def _unescape_ics_value(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _infer_title_and_studio(subject: str) -> tuple[str | None, str | None]:
    cleaned = re.sub(r"^(re|fwd?)\s*:\s*", "", subject, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r"\b(booking confirmation|booking confirmed|confirmed|reservation confirmed|"
        r"buchungsbestaetigung|buchungsbestatigung|buchungsbestätigung|deine buchung|"
        r"your booking|reminder|erinnerung|updated|late cancellation|cancellation confirmed|"
        r"cancellation|cancelled|canceled|stornierung|storniert)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _clean_value(cleaned.strip(" :-"))
    studio = None

    match = re.search(r"(.+?)\s+(?:at|bei|in)\s+(.+)$", cleaned, flags=re.IGNORECASE)
    if match:
        cleaned = _clean_value(match.group(1))
        studio = _clean_value(match.group(2))

    return (cleaned or None, studio or None)


def _sender_display_name(sender: str) -> str | None:
    name, address = parseaddr(sender)
    value = name or address.split("@")[0]
    value = _clean_value(value.replace(".", " "))
    return value or None


def _find_wellpass_studio(lines: list[str]) -> str | None:
    patterns = [
        re.compile(r"\bconfirming your booking at\s+(.+?)(?:\s*\.\s+Here\b|\s*\.?$)", re.IGNORECASE),
        re.compile(r"\bchanges to your booking at\s+(.+?)(?:\s*\.\s+Here\b|\s*\.?$)", re.IGNORECASE),
        re.compile(r"\bcancelled your\s+.+?\s+session at\s+(.+?)\s+on\b", re.IGNORECASE),
        re.compile(r"\bcanceled your\s+.+?\s+session at\s+(.+?)\s+on\b", re.IGNORECASE),
    ]
    for line in lines:
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                return _clean_value(match.group(1))
    return None


def _extract_wellpass_fields(lines: list[str], subject: str) -> dict[str, str]:
    found: dict[str, str] = {}
    text = "\n".join([subject, *lines])
    cancellation_patterns = [
        re.compile(
            r"successfully cancel(?:ed|led) your\s+(.+?)\s+session at\s+(.+?)\s+on\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"Unfortunately,\s+(.+?)\s+had to cancel your booking for\s+(.+?)\s+class\b",
            re.IGNORECASE,
        ),
    ]
    for pattern in cancellation_patterns:
        match = pattern.search(text)
        if not match:
            continue
        if pattern.pattern.startswith("successfully"):
            found["title"] = _clean_value(match.group(1))
            found["studio"] = _clean_value(match.group(2))
        else:
            found["studio"] = _clean_value(match.group(1))
            found["title"] = _clean_value(match.group(2))
        return found

    subject_match = re.search(
        r"(?:cancelled|canceled|cancellation confirmed|late cancellation)\s*:\s*(.+?)\s+at\s+(.+)$",
        subject,
        flags=re.IGNORECASE,
    )
    if subject_match:
        found["title"] = _clean_value(subject_match.group(1))
        found["studio"] = _clean_value(subject_match.group(2))
    for line in lines:
        trainer_match = re.match(r"^Trainer\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
        if trainer_match:
            found["trainer"] = _clean_value(trainer_match.group(1))
    return found


def _clean_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(" -:|")
    value = re.sub(r"^[^\w(]+", "", value, flags=re.UNICODE).strip()
    value = value.strip(" -:|")
    return value


def _find_date(text: str):
    compact = _fold_german_umlauts(text.lower())
    patterns = [
        re.compile(r"\b(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b"),
        re.compile(r"\b(?P<day>\d{1,2})[./-](?P<month>\d{1,2})[./-](?P<year>\d{2,4})\b"),
        re.compile(
            r"\b(?P<day>\d{1,2})\.?\s*(?P<month>"
            + "|".join(sorted(GERMAN_MONTHS, key=len, reverse=True))
            + r")\s*(?P<year>\d{4})\b"
        ),
        re.compile(
            r"\b(?P<month>"
            + "|".join(sorted(ENGLISH_MONTHS, key=len, reverse=True))
            + r")\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?[,]?\s+(?P<year>\d{4})\b"
        ),
    ]
    for pattern in patterns:
        match = pattern.search(compact)
        if not match:
            continue
        groups = match.groupdict()
        day = int(groups["day"])
        year = int(groups["year"])
        if year < 100:
            year += 2000
        month_raw = groups["month"]
        month = int(month_raw) if month_raw.isdigit() else GERMAN_MONTHS.get(month_raw) or ENGLISH_MONTHS[month_raw]
        try:
            return datetime(year, month, day).date()
        except ValueError:
            continue
    return None


def _find_time_range(lines: list[str]):
    pattern = re.compile(
        r"\b(?P<sh>[0-2]?\d)[:.](?P<sm>[0-5]\d)\s*(?P<sampm>am|pm)?\s*(?:uhr)?\s*"
        r"(?:-|bis|to|until|\u2013|\u2014)\s*"
        r"(?P<eh>[0-2]?\d)[:.](?P<em>[0-5]\d)\s*(?P<eampm>am|pm)?\s*(?:uhr)?(?![.\d])\b",
        re.IGNORECASE,
    )
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        from datetime import time

        return (
            time(_hour_with_ampm(match.group("sh"), match.group("sampm")), int(match.group("sm"))),
            time(_hour_with_ampm(match.group("eh"), match.group("eampm")), int(match.group("em"))),
        )
    return None


def _find_single_time(lines: list[str]):
    pattern = re.compile(
        r"\b(?:um|at|beginn(?:t)?(?: um)?|start(?:s)?(?: at)?|von)?\s*"
        r"(?P<h>[0-2]?\d)[:.](?P<m>[0-5]\d)\s*(?P<ampm>am|pm)?\s*(?:uhr)?(?![.\d])\b",
        re.IGNORECASE,
    )
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        from datetime import time

        return time(_hour_with_ampm(match.group("h"), match.group("ampm")), int(match.group("m")))
    return None


def _find_duration_minutes(text: str) -> int | None:
    hour_match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(?:h|hr|hrs|hour|hours|stunde|stunden)\b", text, flags=re.IGNORECASE)
    if hour_match:
        hours = float(hour_match.group(1).replace(",", "."))
        minutes = int(hours * 60)
        if 15 <= minutes <= 240:
            return minutes

    match = re.search(r"\b(\d{2,3})\s*(?:min|minute|minutes|minuten)\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    minutes = int(match.group(1))
    if 15 <= minutes <= 240:
        return minutes
    return None


def _hour_with_ampm(hour: str, ampm: str | None) -> int:
    value = int(hour)
    if not ampm:
        return value
    marker = ampm.lower()
    if marker == "am":
        return 0 if value == 12 else value
    if marker == "pm":
        return value if value == 12 else value + 12
    return value


def _fold_german_umlauts(value: str) -> str:
    return (
        value.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _fingerprint(
    booking_id: str | None,
    title: str,
    studio: str | None,
    start_at: datetime | None,
) -> str:
    if booking_id:
        basis = f"booking-id:{_slug(booking_id)}"
    else:
        start_part = start_at.isoformat(timespec="minutes") if start_at else "unknown-start"
        basis = "|".join([_slug(title), _slug(studio or ""), start_part])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _fold_german_umlauts(value.lower())).strip("-")


def _build_notes(
    source: SourceEmail,
    booking_id: str | None,
    studio: str | None,
    fields: dict[str, str],
) -> str:
    parts = []
    if fields.get("trainer"):
        parts.append(f"Trainer: {fields['trainer']}")
    return "\n".join(parts)
