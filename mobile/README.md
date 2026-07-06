# Wellpass Calendar Sync Mobile

This is the iPhone and Android app source for Wellpass Calendar Sync.

The mobile app uses the same product flow as the desktop app:

1. Choose where Wellpass emails arrive.
2. Choose where calendar events should go.
3. Test run with no calendar changes.
4. Sync now.

## Current State

Implemented:

- Expo app for iOS and Android.
- Simple setup-first UI.
- Mobile TypeScript parser for Wellpass-style booking and cancellation emails.
- Sample test run inside the app.
- EAS build profiles for Android and iOS.
- Unit tests for the mobile parser and sync log.

Still required before public App Store / Play Store release:

- Real mobile OAuth client IDs for Google and Microsoft.
- Apple Developer account and iOS signing credentials.
- Android keystore and Play Console setup.
- Provider adapters that call Gmail, Microsoft Graph, Google Calendar, Outlook Calendar, and CalDAV from mobile.
- Background sync policy decisions. iOS background execution is best-effort, not a reliable scheduler like desktop Task Scheduler or LaunchAgent.

## Run Locally

```bash
cd mobile
npm install
npm run test
npm run typecheck
npm run start
```

## Build

With EAS configured:

```bash
cd mobile
npx eas build --platform android --profile preview
npx eas build --platform ios --profile preview
```

Production iOS builds require an Apple Developer account. Production Android builds require an Android signing key.
