# Wellpass Calendar Sync

Sync Wellpass booking and cancellation emails into your calendar.

Download the app, connect your email and calendar, run a dry run, then turn on automatic sync. No terminal is needed for normal use.

This project is not affiliated with Wellpass, EGYM, Apple, Google, or Microsoft.

## What It Does

- Reads Wellpass booking, update, and cancellation emails.
- Adds confirmed bookings to a calendar.
- Removes cancelled bookings from the calendar.
- Uses the `.ics` attachment address when available, so locations are more likely to be clickable on phones.
- Keeps local state so the same email is not processed twice.
- Shows clear logs for created, updated, skipped, ignored, and cancelled events.
- Can run manually or on a schedule.

## Download

Use the latest [GitHub Release](https://github.com/cakirmert/well/releases/latest).

1. Open the repository's `Releases` page.
2. Download the file for your operating system.
3. Unzip it if needed.
4. Open the app.

Release downloads:

- Windows: `WellpassCalendarSync-Windows.zip`
- macOS: `WellpassCalendarSync-macOS.zip`
- Linux: `WellpassCalendarSync-Linux.tar.gz`

On Windows, unzip the file and open `WellpassCalendarSync.exe`.

On macOS, unzip the file and open the included app or executable. If macOS blocks it because it is not notarized yet, right-click it and choose `Open`.

## Mobile App

The iPhone and Android app source lives in [`mobile`](mobile/).

Current mobile status:

- Expo app for iOS and Android.
- Same setup-first flow as desktop.
- Mobile parser and sample sync log are implemented and tested.
- Gmail and Google Calendar adapters are wired for OAuth client IDs.
- Phone Calendar target is wired for iOS/Android calendar permission. On iPhone, this can write to iCloud calendars already configured on the phone.
- EAS build profiles are included for Android and iOS.

Not released to App Store or Play Store yet:

- iOS release builds need an Apple Developer account and signing credentials.
- Android release builds need a signing key and Play Console setup.
- Public Gmail access may need Google OAuth verification because Gmail read access is a restricted scope.
- Microsoft Outlook and generic IMAP mobile adapters are still planned.
- iOS background sync is best-effort. Desktop scheduling remains more reliable for automatic sync.

## First Setup

1. Open the app.
2. On `Setup`, choose where your Wellpass emails arrive.
3. Sign in or save the email password if the app asks for one.
4. Choose where calendar events should go.
5. Sign in or save the calendar password if the app asks for one.
6. Click `Find calendars`.
7. Choose an existing calendar or type a new calendar name such as `Wellpass`.
8. Click `Test run - no changes`.
9. If the log looks correct, click `Sync now`.
10. Open `Automatic Sync` and turn it on if you want background sync.

The `Advanced` tab is only for troubleshooting or unusual providers.

The app creates its own local config automatically:

- Windows: `%APPDATA%\Wellpass Calendar Sync\.env`
- macOS: `~/Library/Application Support/Wellpass Calendar Sync/.env`
- Linux: `~/.config/wellpass-calendar-sync/.env` unless `XDG_CONFIG_HOME` is set.

## Supported Providers

Email sources:

- Outlook.com / Microsoft 365 through Microsoft Graph OAuth.
- Gmail through native Google OAuth.
- Generic IMAP for providers such as iCloud Mail, Yahoo, Fastmail, and custom mailboxes.
- Classic Windows desktop Outlook as a local fallback.

Calendar targets:

- iCloud Calendar through CalDAV.
- Google Calendar through Google OAuth.
- Outlook Calendar through Microsoft Graph.
- Generic `.ics` export for testing or fallback.

No app can truly support every provider with one identical login flow because providers use different OAuth, IMAP, app-password, and admin-policy rules. This app supports the common paths directly and keeps the provider code modular.

## Calendar Choice

You can use a dedicated calendar to avoid polluting your main calendar.

Recommended names:

- `Wellpass`
- `Sport`

If the configured calendar does not exist, supported writable targets create it during sync. You can also pick an existing calendar from the GUI.

## Scheduling

The app supports two scheduling modes.

In-app scheduling:

- Runs while the app window is open.
- Can be started and stopped from the `Schedule` tab.

OS scheduling:

- Windows: Task Scheduler.
- macOS: LaunchAgent.
- Linux: systemd user timer.
- Continues to work after the app window is closed.

When installed from the packaged app, the scheduler reuses that same app executable for background sync.

## Passwords and Sign-In

Passwords are stored in the OS keychain:

- Windows: Windows Credential Manager.
- macOS: Keychain.
- Linux: Secret Service / KWallet, depending on the desktop.

For iCloud Calendar, use an Apple app-specific password, not your normal Apple Account password.

For Outlook.com / Microsoft 365, use `Sign in with Microsoft`.

For Gmail or Google Calendar, use `Sign in with Google`. The desktop app can use a local OAuth client JSON. The mobile app uses iOS and Android OAuth client IDs configured through `mobile/.env` before building.

## Safe Defaults

- Timezone defaults to `Europe/Berlin`.
- The email search window defaults to 30 days.
- The app starts with dry-run behavior in config.
- Local SQLite state prevents duplicate processing.
- Token caches, SQLite databases, exported calendars, `.env`, and build output are ignored by git.

## Build From Source

For developers:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[packaging]"
python tools\build_executable.py
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[packaging]"
python tools/build_executable.py
```

Builds are OS-specific. Build on Windows for a Windows executable, macOS for a macOS artifact, and Linux for a Linux artifact.

Mobile app:

```bash
cd mobile
npm install
npm run test
npm run typecheck
npm run start
```

Mobile store builds use EAS:

```bash
cd mobile
npx eas build --platform android --profile production
npx eas build --platform ios --profile production
```

## Tests

```powershell
python -m unittest discover -s tests
```

The parser tests use redacted `.eml` fixtures under `tests/fixtures`.

## Release Checklist

Before publishing a release:

1. Run tests.
2. Build the executable locally or with GitHub Actions.
3. Open the executable and verify the GUI starts.
4. Verify `Dry Run` logs the expected created/skipped/cancelled actions.
5. Confirm `.env`, token caches, SQLite DBs, and build internals are not committed.
6. Push a version tag such as `v0.1.0`.
7. GitHub Actions builds Windows, macOS, and Linux downloads.
8. The workflow publishes the GitHub Release automatically.
