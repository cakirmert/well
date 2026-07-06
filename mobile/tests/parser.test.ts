import { describe, expect, it } from "vitest";

import { base64UrlDecode, parseGmailEmailsForPreview } from "../src/providers/googleApi";
import { parseBookingEmail, sourceEmailFromRaw } from "../src/core/parser";
import { runSampleSync } from "../src/core/sampleSync";

describe("mobile Wellpass parser", () => {
  it("parses a booking confirmation", () => {
    const source = sourceEmailFromRaw(`From: Wellpass <noreply-de@egym-wellpass.com>
Subject: Booking Confirmed: Mobility Yoga at Urban Sports Studio
Message-ID: <booking@example>

Booking ID: WB-12345
Booked: Mobility Yoga
Studio: Urban Sports Studio
Date: July 2, 2026
Time: 18:30 - 19:30
Address: Mainzer Str. 1, 10115 Berlin
Trainer: Alex
`);

    const event = parseBookingEmail(source);

    expect(event).not.toBeNull();
    expect(event?.status).toBe("confirmed");
    expect(event?.bookingId).toBe("WB-12345");
    expect(event?.title).toBe("Mobility Yoga");
    expect(event?.studio).toBe("Urban Sports Studio");
    expect(event?.location).toBe("Mainzer Str. 1, 10115 Berlin");
    expect(event?.startAt).toBe("2026-07-02T18:30:00+02:00");
    expect(event?.endAt).toBe("2026-07-02T19:30:00+02:00");
    expect(event?.notes).toBe("Trainer: Alex");
  });

  it("parses cancellation emails", () => {
    const source = sourceEmailFromRaw(`From: Wellpass <noreply-de@egym-wellpass.com>
Subject: Cancellation Confirmed: Mobility Yoga at Urban Sports Studio
Message-ID: <cancel@example>

Booking ID: WB-12345
Class: Mobility Yoga
Studio: Urban Sports Studio
Date: July 2, 2026
Time: 18:30 - 19:30
Your cancellation is confirmed.
`);

    const event = parseBookingEmail(source);

    expect(event?.status).toBe("cancelled");
    expect(event?.bookingId).toBe("WB-12345");
    expect(event?.title).toBe("Mobility Yoga");
  });

  it("produces friendly sample sync logs", () => {
    const logs = runSampleSync(false).map((entry) => entry.message);

    expect(logs).toContain("Checked 2 sample Wellpass email(s).");
    expect(logs.some((line) => line.startsWith("Would add: Mobility Yoga"))).toBe(true);
    expect(logs.some((line) => line.startsWith("Would remove: Mobility Yoga"))).toBe(true);
    expect(logs).toContain("Test run only. Your calendar was not changed.");
  });

  it("decodes Gmail raw messages and parses them for preview", () => {
    const raw = `From: Wellpass <noreply-de@egym-wellpass.com>
Subject: Booking Confirmed: Flow at Studio
Message-ID: <gmail-example>

Booking ID: WB-987
Booked: Flow
Studio: Studio
Date: July 3, 2026
Time: 09:00 - 10:00
`;
    const encoded = btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const decoded = base64UrlDecode(encoded);
    const events = parseGmailEmailsForPreview([sourceEmailFromRaw(decoded)]);

    expect(events).toHaveLength(1);
    expect(events[0]?.title).toBe("Flow");
    expect(events[0]?.startAt).toBe("2026-07-03T09:00:00+02:00");
  });
});
