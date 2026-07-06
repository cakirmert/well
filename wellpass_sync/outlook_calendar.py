from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .calendar import CalendarWriteResult, CalendarWriter
from .config import AppConfig
from .graph_mail import GRAPH_ROOT, get_graph_access_token
from .models import BookingEvent

OUTLOOK_CALENDAR_SCOPE = "Calendars.ReadWrite"


class OutlookCalendarWriter(CalendarWriter):
    def __init__(self, config: AppConfig) -> None:
        self._token = get_graph_access_token(config, scopes=_with_calendar_scope(config.graph_scopes))
        self._calendar_id = _get_or_create_calendar(self._token, config.calendar_name)
        self._timezone = config.timezone
        self._reminder_minutes = config.reminder_minutes

    def upsert_event(self, event: BookingEvent, existing_href: str | None = None) -> CalendarWriteResult:
        body = _graph_event_body(event, self._timezone, self._reminder_minutes)
        if existing_href:
            try:
                payload = _graph_json(
                    f"{GRAPH_ROOT}/me/calendars/{_quote(self._calendar_id)}/events/{_quote(existing_href)}",
                    self._token,
                    method="PATCH",
                    body=body,
                )
                return CalendarWriteResult(action="updated", href=payload.get("id") or existing_href)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
        payload = _graph_json(
            f"{GRAPH_ROOT}/me/calendars/{_quote(self._calendar_id)}/events",
            self._token,
            method="POST",
            body=body,
        )
        return CalendarWriteResult(action="created", href=payload.get("id"))

    def cancel_event(
        self,
        calendar_uid: str,
        fallback_event: BookingEvent | None = None,
        existing_href: str | None = None,
    ) -> CalendarWriteResult:
        if not existing_href:
            return CalendarWriteResult(action="missing", href=None)
        try:
            _graph_json(
                f"{GRAPH_ROOT}/me/calendars/{_quote(self._calendar_id)}/events/{_quote(existing_href)}",
                self._token,
                method="DELETE",
                expect_json=False,
            )
            return CalendarWriteResult(action="deleted", href=existing_href)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return CalendarWriteResult(action="missing", href=existing_href)
            raise


def list_outlook_calendar_names(config: AppConfig) -> list[str]:
    token = get_graph_access_token(config, scopes=_with_calendar_scope(config.graph_scopes))
    response = _graph_json(f"{GRAPH_ROOT}/me/calendars", token)
    return sorted(item.get("name", "") for item in response.get("value", []) if item.get("name"))


def _get_or_create_calendar(token: str, calendar_name: str) -> str:
    response = _graph_json(f"{GRAPH_ROOT}/me/calendars", token)
    for item in response.get("value", []):
        if item.get("name") == calendar_name:
            return item["id"]
    created = _graph_json(f"{GRAPH_ROOT}/me/calendars", token, method="POST", body={"name": calendar_name})
    return created["id"]


def _graph_event_body(event: BookingEvent, timezone_name: str, reminder_minutes: list[int]) -> dict:
    if not event.start_at or not event.end_at:
        raise ValueError("Cannot write Outlook Calendar event without start/end datetimes")
    body = {
        "subject": event.title,
        "body": {"contentType": "text", "content": event.notes or ""},
        "start": {"dateTime": event.start_at.replace(tzinfo=None).isoformat(), "timeZone": timezone_name},
        "end": {"dateTime": event.end_at.replace(tzinfo=None).isoformat(), "timeZone": timezone_name},
        "showAs": "busy",
        "transactionId": event.calendar_uid,
        "singleValueExtendedProperties": [
            {
                "id": "String {00020329-0000-0000-C000-000000000046} Name wellpassSyncUid",
                "value": event.calendar_uid,
            }
        ],
    }
    if event.location:
        body["location"] = {"displayName": event.location}
    if reminder_minutes:
        body["isReminderOn"] = True
        body["reminderMinutesBeforeStart"] = min(set(reminder_minutes))
    else:
        body["isReminderOn"] = False
    return body


def _graph_json(
    url: str,
    token: str,
    method: str = "GET",
    body: dict | None = None,
    expect_json: bool = True,
) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if not expect_json or response.status == 204:
            return {}
        return json.loads(response.read().decode("utf-8"))


def _with_calendar_scope(scopes: list[str]) -> list[str]:
    return sorted(set(scopes) | {OUTLOOK_CALENDAR_SCOPE})


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")
