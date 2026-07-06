from __future__ import annotations

import unittest

from wellpass_sync.google_calendar import _google_event_body, _google_event_id
from wellpass_sync.outlook_calendar import _graph_event_body
from wellpass_sync.parser import parse_booking_email, source_email_from_bytes


class ProviderPayloadTests(unittest.TestCase):
    def test_google_event_body_uses_timezone_location_and_reminders(self):
        event = _event()
        body = _google_event_body(event, "Europe/Berlin", [1440, 60])

        self.assertEqual(body["summary"], "Pilates")
        self.assertEqual(body["location"], "Barmbeker Strasse 26B, Hamburg")
        self.assertEqual(body["start"]["timeZone"], "Europe/Berlin")
        self.assertEqual(body["reminders"]["useDefault"], False)
        self.assertEqual(
            sorted(item["minutes"] for item in body["reminders"]["overrides"]),
            [60, 1440],
        )
        self.assertEqual(len(_google_event_id(event.calendar_uid)), 40)

    def test_outlook_event_body_uses_timezone_location_and_reminder(self):
        event = _event()
        body = _graph_event_body(event, "Europe/Berlin", [1440, 60])

        self.assertEqual(body["subject"], "Pilates")
        self.assertEqual(body["location"]["displayName"], "Barmbeker Strasse 26B, Hamburg")
        self.assertEqual(body["start"]["timeZone"], "Europe/Berlin")
        self.assertEqual(body["isReminderOn"], True)
        self.assertEqual(body["reminderMinutesBeforeStart"], 60)
        self.assertEqual(
            body["singleValueExtendedProperties"][0]["value"],
            event.calendar_uid,
        )


def _event():
    raw = b"""From: Wellpass <noreply-de@egym-wellpass.com>
Subject: Booking Confirmed: Pilates at Align Hamburg
Message-ID: <provider-payload-test@example>
Content-Type: text/plain; charset=utf-8

Booked: Pilates
Date: Friday, July 3, 2026
Time: 9:00 AM
Duration: 45 minutes
Address: Barmbeker Strasse 26B, Hamburg
"""
    event = parse_booking_email(source_email_from_bytes(raw), "Europe/Berlin")
    assert event is not None
    return event


if __name__ == "__main__":
    unittest.main()
