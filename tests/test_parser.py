from __future__ import annotations

import unittest
from pathlib import Path

from wellpass_sync.models import EmailAttachment, SourceEmail
from wellpass_sync.parser import parse_booking_email, source_email_from_bytes


FIXTURES = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def parse_fixture(self, name: str):
        source = source_email_from_bytes((FIXTURES / name).read_bytes())
        event = parse_booking_email(source, "Europe/Berlin")
        self.assertIsNotNone(event)
        return event

    def test_booking_confirmation(self):
        event = self.parse_fixture("booking-confirmation.eml")
        self.assertEqual(event.status, "confirmed")
        self.assertEqual(event.booking_id, "WB-12345")
        self.assertEqual(event.title, "Mobility Yoga")
        self.assertEqual(event.studio, "Urban Sports Studio")
        self.assertEqual(event.location, "Mainzer Str. 1, 10115 Berlin")
        self.assertEqual(event.start_at.isoformat(), "2026-07-02T18:30:00+02:00")
        self.assertEqual(event.end_at.isoformat(), "2026-07-02T19:30:00+02:00")

    def test_partner_booking_with_duration(self):
        event = self.parse_fixture("partner-booking.eml")
        self.assertEqual(event.status, "confirmed")
        self.assertEqual(event.title, "Functional Training")
        self.assertEqual(event.start_at.isoformat(), "2026-07-04T07:15:00+02:00")
        self.assertEqual(event.end_at.isoformat(), "2026-07-04T08:00:00+02:00")

    def test_cancellation(self):
        event = self.parse_fixture("cancellation.eml")
        self.assertEqual(event.status, "cancelled")
        self.assertEqual(event.booking_id, "WB-12345")
        self.assertEqual(event.title, "Mobility Yoga")

    def test_ics_attachment_location_wins_and_does_not_change_fingerprint(self):
        source = SourceEmail(
            message_id="<ics-location-test>",
            subject="Booking Confirmed: Pilates x Stretch at Align Hamburg",
            sender="Wellpass <noreply-de@egym-wellpass.com>",
            sent_at=None,
            body_text="Hello Mert, We are confirming your booking at Align Hamburg.",
            raw_bytes=b"ics-location-test",
            attachments=(
                EmailAttachment(
                    filename="booking.ics",
                    content_type="text/calendar",
                    content=(
                        "BEGIN:VCALENDAR\r\n"
                        "BEGIN:VEVENT\r\n"
                        "UID:test-1\r\n"
                        "SUMMARY:Pilates x Stretch\r\n"
                        "DTSTART;TZID=Europe/Berlin:20260702T081000\r\n"
                        "DTEND;TZID=Europe/Berlin:20260702T090000\r\n"
                        "LOCATION:Barmbeker Stra\u00dfe 26B\\, 22303 Hamburg\\, DE\r\n"
                        "END:VEVENT\r\n"
                        "END:VCALENDAR\r\n"
                    ).encode("utf-8"),
                ),
            ),
        )
        event = parse_booking_email(source, "Europe/Berlin")
        self.assertIsNotNone(event)
        self.assertEqual(event.location, "Barmbeker Stra\u00dfe 26B, 22303 Hamburg, DE")

        changed_location = SourceEmail(
            **{
                **source.__dict__,
                "message_id": "<ics-location-test-2>",
                "attachments": (
                    EmailAttachment(
                        filename="booking.ics",
                        content_type="text/calendar",
                        content=(
                            "BEGIN:VCALENDAR\r\n"
                            "BEGIN:VEVENT\r\n"
                            "UID:test-1\r\n"
                            "SUMMARY:Pilates x Stretch\r\n"
                            "DTSTART;TZID=Europe/Berlin:20260702T081000\r\n"
                            "DTEND;TZID=Europe/Berlin:20260702T090000\r\n"
                            "LOCATION:Different Street 1\\, 22303 Hamburg\\, DE\r\n"
                            "END:VEVENT\r\n"
                            "END:VCALENDAR\r\n"
                        ).encode("utf-8"),
                    ),
                ),
            }
        )
        changed_event = parse_booking_email(changed_location, "Europe/Berlin")
        self.assertIsNotNone(changed_event)
        self.assertEqual(event.fingerprint, changed_event.fingerprint)


if __name__ == "__main__":
    unittest.main()
