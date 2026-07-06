# Requirements

## Must Have

- Run locally on Windows, macOS, and Linux desktop environments.
- Read booking and cancellation emails.
- Add bookings automatically to a calendar.
- Support iCloud Calendar via CalDAV as the preferred target.
- Support Google Calendar as a native target.
- Support Outlook Calendar as a native target.
- Support native Gmail OAuth for reading booking emails.
- Deduplicate processed emails and calendar events.
- Support `dry-run` before writing to calendar.
- Support `run once` mode.
- Be schedulable through the host operating system.
- Offer a GUI for non-terminal setup and manual sync.

## Should Have

- Parser tests based on redacted `.eml` samples.
- Dedicated `Wellpass` calendar to avoid polluting the main calendar.
- Clear logs for created, updated, skipped, and canceled events.
- Safe handling of timezones, defaulting to `Europe/Berlin`.
- Mobile app shell for iPhone and Android with the same setup-first flow.

## Could Have Later

- Tray icon with background status.
- Fully connected iPhone and Android provider adapters.
- App Store and Play Store releases.
- Wellpass login integration if email parsing is insufficient.
- Background tray app.
- Hosted server version.

## Non-Goals For MVP

- Scraping the Wellpass app or website.
- Running on a public server.
- Claiming reliable iOS background scheduling before real-device testing.
- Handling every possible studio email format before real examples are provided.
- Storing plain credentials in source code.

## Best Operating Model

Start with a local run-once CLI plus a GUI that can trigger manual syncs and control scheduling. OS schedulers are the durable background option: Task Scheduler on Windows, LaunchAgent on macOS, and systemd user timers on Linux. A server is only worth it later if the PC is often off, multiple devices/users need sync, or push-based real-time sync becomes important.
