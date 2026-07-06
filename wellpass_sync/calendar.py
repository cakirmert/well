from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import AppConfig
from .models import BookingEvent


@dataclass(frozen=True)
class CalendarWriteResult:
    action: str
    href: str | None = None


class CalendarWriter:
    def upsert_event(self, event: BookingEvent, existing_href: str | None = None) -> CalendarWriteResult:
        raise NotImplementedError

    def cancel_event(
        self,
        calendar_uid: str,
        fallback_event: BookingEvent | None = None,
        existing_href: str | None = None,
    ) -> CalendarWriteResult:
        raise NotImplementedError


class IcsExportCalendar(CalendarWriter):
    def __init__(self, export_dir: str | Path, reminder_minutes: list[int] | None = None) -> None:
        self.export_dir = Path(export_dir)
        self.reminder_minutes = reminder_minutes or []
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def upsert_event(self, event: BookingEvent, existing_href: str | None = None) -> CalendarWriteResult:
        path = self.export_dir / f"{_safe_uid(event.calendar_uid)}.ics"
        path.write_text(build_ics(event, reminder_minutes=self.reminder_minutes), encoding="utf-8")
        return CalendarWriteResult(action="exported", href=str(path))

    def cancel_event(
        self,
        calendar_uid: str,
        fallback_event: BookingEvent | None = None,
        existing_href: str | None = None,
    ) -> CalendarWriteResult:
        if fallback_event:
            path = self.export_dir / f"{_safe_uid(calendar_uid)}.ics"
            path.write_text(
                build_ics(
                    fallback_event,
                    force_cancelled=True,
                    reminder_minutes=self.reminder_minutes,
                ),
                encoding="utf-8",
            )
            return CalendarWriteResult(action="cancel-exported", href=str(path))
        path = self.export_dir / f"{_safe_uid(calendar_uid)}.ics"
        if path.exists():
            path.unlink()
            return CalendarWriteResult(action="deleted-export", href=str(path))
        return CalendarWriteResult(action="missing-export", href=str(path))


class ICloudCalDavCalendar(CalendarWriter):
    def __init__(self, config: AppConfig) -> None:
        config.validate_calendar_write()
        try:
            import caldav
        except ImportError as exc:
            raise RuntimeError(
                "The 'caldav' package is required for iCloud writes. "
                "Install dependencies with: python -m pip install -e ."
            ) from exc

        self._caldav = caldav
        self._client = caldav.DAVClient(
            url=config.caldav_url,
            username=config.icloud_username,
            password=config.icloud_app_password,
        )
        self._calendar = self._get_or_create_calendar(config.calendar_name)
        self._reminder_minutes = config.reminder_minutes

    def upsert_event(self, event: BookingEvent, existing_href: str | None = None) -> CalendarWriteResult:
        ics = build_ics(event, reminder_minutes=self._reminder_minutes)
        saved = self._calendar.add_event(ics)
        return CalendarWriteResult(action="saved", href=_href(saved))

    def cancel_event(
        self,
        calendar_uid: str,
        fallback_event: BookingEvent | None = None,
        existing_href: str | None = None,
    ) -> CalendarWriteResult:
        event = self._caldav.Event(
            self._client,
            url=existing_href or self._event_url(calendar_uid),
            parent=self._calendar,
        )
        try:
            event.delete()
            return CalendarWriteResult(action="deleted", href=_href(event))
        except Exception as exc:
            if _is_missing(exc):
                return CalendarWriteResult(action="missing", href=_href(event))
            raise

    def _get_or_create_calendar(self, calendar_name: str):
        principal = self._client.principal()
        for calendar in principal.calendars():
            display_name = _calendar_display_name(calendar)
            if display_name == calendar_name:
                return calendar
        return principal.make_calendar(name=calendar_name)

    def _event_by_uid(self, uid: str):
        try:
            return self._calendar.event_by_uid(uid)
        except Exception as exc:
            if _is_missing(exc):
                return None
            raise

    def _event_url(self, uid: str) -> str:
        filename = urllib.parse.quote(uid, safe="") + ".ics"
        return str(self._calendar.url).rstrip("/") + "/" + filename


def _href(resource) -> str | None:
    value = getattr(resource, "url", None)
    if value is None:
        return None
    return str(value)


def _is_missing(exc: Exception) -> bool:
    name = exc.__class__.__name__.lower()
    status = getattr(exc, "status", None)
    text = str(exc).lower()
    return "notfound" in name or status == 404 or "404" in text


def make_calendar_writer(config: AppConfig, force_ics: bool = False) -> CalendarWriter:
    if force_ics or config.calendar_provider == "ics":
        return IcsExportCalendar(config.ics_export_dir, config.reminder_minutes)
    if config.calendar_provider in {"icloud_caldav", "caldav"}:
        return ICloudCalDavCalendar(config)
    if config.calendar_provider == "google_calendar":
        from .google_calendar import GoogleCalendarWriter

        return GoogleCalendarWriter(config)
    if config.calendar_provider == "outlook_calendar":
        from .outlook_calendar import OutlookCalendarWriter

        return OutlookCalendarWriter(config)
    raise ValueError(f"Unsupported CALENDAR_PROVIDER={config.calendar_provider!r}")


def calendar_exists(config: AppConfig, calendar_name: str) -> bool:
    if config.calendar_provider == "ics":
        return False
    if config.calendar_provider == "google_calendar":
        from .google_calendar import list_google_calendar_names

        return calendar_name.lower() in {name.lower() for name in list_google_calendar_names(config)}
    if config.calendar_provider == "outlook_calendar":
        from .outlook_calendar import list_outlook_calendar_names

        return calendar_name.lower() in {name.lower() for name in list_outlook_calendar_names(config)}
    config.validate_calendar_write()
    try:
        import caldav
    except ImportError as exc:
        raise RuntimeError(
            "The 'caldav' package is required for iCloud checks. "
            "Install dependencies with: .\\.venv\\Scripts\\python.exe -m pip install -e ."
        ) from exc

    client = caldav.DAVClient(
        url=config.caldav_url,
        username=config.icloud_username,
        password=config.icloud_app_password,
    )
    principal = client.principal()
    wanted = calendar_name.lower()
    for calendar in principal.calendars():
        if _calendar_display_name(calendar).lower() == wanted:
            return True
    return False


def list_calendar_names(config: AppConfig) -> list[str]:
    if config.calendar_provider == "ics":
        return []
    if config.calendar_provider == "google_calendar":
        from .google_calendar import list_google_calendar_names

        return list_google_calendar_names(config)
    if config.calendar_provider == "outlook_calendar":
        from .outlook_calendar import list_outlook_calendar_names

        return list_outlook_calendar_names(config)
    config.validate_calendar_write()
    try:
        import caldav
    except ImportError as exc:
        raise RuntimeError(
            "The 'caldav' package is required for iCloud checks. "
            "Install dependencies with: python -m pip install -e ."
        ) from exc

    client = caldav.DAVClient(
        url=config.caldav_url,
        username=config.icloud_username,
        password=config.icloud_app_password,
    )
    principal = client.principal()
    return sorted(_calendar_display_name(calendar) for calendar in principal.calendars())


def build_ics(
    event: BookingEvent,
    force_cancelled: bool = False,
    reminder_minutes: list[int] | None = None,
) -> str:
    if not event.start_at or not event.end_at:
        raise ValueError("Cannot build ICS for event without start/end datetimes")

    status = "CANCELLED" if force_cancelled or event.status == "cancelled" else "CONFIRMED"
    now = datetime.now(timezone.utc)
    start = _utc_stamp(event.start_at)
    end = _utc_stamp(event.end_at)
    description = event.notes

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Local Wellpass Sync//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{_escape_ical(event.calendar_uid)}",
        f"DTSTAMP:{_format_utc(now)}",
        f"DTSTART:{start}",
        f"DTEND:{end}",
        f"SUMMARY:{_escape_ical(event.title)}",
        f"STATUS:{status}",
        f"DESCRIPTION:{_escape_ical(description)}",
    ]
    if event.location:
        lines.append(f"LOCATION:{_escape_ical(event.location)}")
    if status != "CANCELLED":
        for minutes in sorted(set(reminder_minutes or []), reverse=True):
            if minutes <= 0:
                continue
            lines.extend(
                [
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_escape_ical(event.title)}",
                    f"TRIGGER:-{_duration(minutes)}",
                    "END:VALARM",
                ]
            )
    lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
    return "\r\n".join(_fold_ical_line(line) for line in lines)


def row_to_event(row) -> BookingEvent:
    start_at = _parse_datetime(row["start_at"], row["timezone"])
    end_at = _parse_datetime(row["end_at"], row["timezone"])
    return BookingEvent(
        source_message_id=row["last_message_id"] or "",
        source_subject="",
        source_sender="",
        booking_id=row["booking_id"],
        title=row["title"],
        studio=row["studio"],
        start_at=start_at,
        end_at=end_at,
        timezone=row["timezone"],
        location=row["location"],
        status=row["status"],
        fingerprint=row["fingerprint"],
        calendar_uid=row["calendar_uid"],
        notes="Created by local Wellpass calendar sync.",
    )


def _parse_datetime(value: str, timezone_name: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed


def _calendar_display_name(calendar) -> str:
    get_display_name = getattr(calendar, "get_display_name", None)
    if callable(get_display_name):
        value = get_display_name()
        if value:
            return str(value)
    name = getattr(calendar, "name", None)
    if callable(name):
        name = name()
    return str(name or "")


def _utc_stamp(value: datetime) -> str:
    return _format_utc(value.astimezone(timezone.utc))


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape_ical(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _fold_ical_line(line: str) -> str:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    chunks: list[str] = []
    current = ""
    current_len = 0
    for char in line:
        char_len = len(char.encode("utf-8"))
        if current and current_len + char_len > 73:
            chunks.append(current)
            current = " " + char
            current_len = 1 + char_len
        else:
            current += char
            current_len += char_len
    chunks.append(current)
    return "\r\n".join(chunks)


def _safe_uid(uid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", uid)


def _duration(minutes: int) -> str:
    days, remainder = divmod(minutes, 24 * 60)
    hours, mins = divmod(remainder, 60)
    date_part = f"{days}D" if days else ""
    time_parts = ""
    if hours:
        time_parts += f"{hours}H"
    if mins:
        time_parts += f"{mins}M"
    if time_parts:
        return f"P{date_part}T{time_parts}"
    return f"P{date_part or '0D'}"
