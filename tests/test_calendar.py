from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from wellpass_sync.calendar import calendar_exists, build_ics, list_calendar_names
from wellpass_sync.config import load_config
from wellpass_sync.parser import parse_booking_email, source_email_from_bytes


class CalendarTests(unittest.TestCase):
    def test_build_ics_includes_one_day_and_one_hour_reminders(self):
        raw = b"""From: Wellpass <noreply-de@egym-wellpass.com>
Subject: Booking Confirmed: Pilates at Align Hamburg
Message-ID: <alarm-test@example>
Content-Type: text/plain; charset=utf-8

Booked: Pilates
Date: Friday, July 3, 2026
Time: 9:00 AM
Duration: 45 minutes
Address: Barmbeker Strasse 26B, Hamburg
"""
        event = parse_booking_email(source_email_from_bytes(raw), "Europe/Berlin")
        self.assertIsNotNone(event)
        ics = build_ics(event, reminder_minutes=[1440, 60])
        self.assertIn("TRIGGER:-P1D", ics)
        self.assertIn("TRIGGER:-PT1H", ics)
        self.assertEqual(ics.count("BEGIN:VALARM"), 2)

    def test_ics_provider_has_no_remote_calendar_list(self):
        config = replace(load_config(Path("missing-test.env")), calendar_provider="ics")

        self.assertEqual(list_calendar_names(config), [])
        self.assertFalse(calendar_exists(config, "Wellpass"))


if __name__ == "__main__":
    unittest.main()
