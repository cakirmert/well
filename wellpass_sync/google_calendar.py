from __future__ import annotations

import hashlib

from googleapiclient.errors import HttpError

from .calendar import CalendarWriteResult, CalendarWriter
from .config import AppConfig
from .google_auth import GOOGLE_CALENDAR_SCOPE, build_google_service
from .models import BookingEvent


class GoogleCalendarWriter(CalendarWriter):
    def __init__(self, config: AppConfig) -> None:
        self._service = build_google_service(config, "calendar", "v3", [GOOGLE_CALENDAR_SCOPE])
        self._calendar_id = _get_or_create_calendar(self._service, config.calendar_name, config.timezone)
        self._timezone = config.timezone
        self._reminder_minutes = config.reminder_minutes

    def upsert_event(self, event: BookingEvent, existing_href: str | None = None) -> CalendarWriteResult:
        event_id = existing_href or _google_event_id(event.calendar_uid)
        body = _google_event_body(event, self._timezone, self._reminder_minutes)
        try:
            self._service.events().update(
                calendarId=self._calendar_id,
                eventId=event_id,
                body={**body, "id": event_id},
            ).execute()
            return CalendarWriteResult(action="updated", href=event_id)
        except HttpError as exc:
            if getattr(exc.resp, "status", None) != 404:
                raise
        self._service.events().insert(
            calendarId=self._calendar_id,
            body={**body, "id": event_id},
        ).execute()
        return CalendarWriteResult(action="created", href=event_id)

    def cancel_event(
        self,
        calendar_uid: str,
        fallback_event: BookingEvent | None = None,
        existing_href: str | None = None,
    ) -> CalendarWriteResult:
        event_id = existing_href or _google_event_id(calendar_uid)
        try:
            self._service.events().delete(calendarId=self._calendar_id, eventId=event_id).execute()
            return CalendarWriteResult(action="deleted", href=event_id)
        except HttpError as exc:
            if getattr(exc.resp, "status", None) == 404:
                return CalendarWriteResult(action="missing", href=event_id)
            raise


def list_google_calendar_names(config: AppConfig) -> list[str]:
    service = build_google_service(config, "calendar", "v3", [GOOGLE_CALENDAR_SCOPE])
    calendars: list[str] = []
    page_token = None
    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        calendars.extend(item.get("summary", "") for item in response.get("items", []) if item.get("summary"))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return sorted(calendars)


def _get_or_create_calendar(service, calendar_name: str, timezone_name: str) -> str:
    page_token = None
    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        for item in response.get("items", []):
            if item.get("summary") == calendar_name:
                return item["id"]
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    created = service.calendars().insert(body={"summary": calendar_name, "timeZone": timezone_name}).execute()
    return created["id"]


def _google_event_body(event: BookingEvent, timezone_name: str, reminder_minutes: list[int]) -> dict:
    if not event.start_at or not event.end_at:
        raise ValueError("Cannot write Google Calendar event without start/end datetimes")
    body = {
        "summary": event.title,
        "description": event.notes,
        "start": {"dateTime": event.start_at.isoformat(), "timeZone": event.timezone or timezone_name},
        "end": {"dateTime": event.end_at.isoformat(), "timeZone": event.timezone or timezone_name},
        "extendedProperties": {"private": {"wellpassCalendarUid": event.calendar_uid}},
    }
    if event.location:
        body["location"] = event.location
    if reminder_minutes:
        body["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": minutes} for minutes in sorted(set(reminder_minutes))],
        }
    else:
        body["reminders"] = {"useDefault": True}
    return body


def _google_event_id(calendar_uid: str) -> str:
    return hashlib.sha1(calendar_uid.encode("utf-8")).hexdigest()
