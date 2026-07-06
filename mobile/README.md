# Wellpass Calendar Sync Mobile

This folder contains the iPhone and Android app.

The mobile app is intentionally simple:

1. Choose the account where Wellpass emails arrive.
2. Choose the calendar target.
3. Run a test with no calendar changes.
4. Sync now.

## What Works Now

- Google sign-in wiring for Gmail and Google Calendar.
- Gmail message search for Wellpass sender emails from the last 30 days.
- Google Calendar create/update/cancel into a chosen calendar name.
- Phone Calendar target through native iOS/Android calendar permission.
- On iPhone, Phone Calendar can write to iCloud calendars already configured on the device.
- Secure Google token storage through `expo-secure-store`.
- Local processed-message tracking through AsyncStorage.
- Parser tests for booking and cancellation emails.
- EAS build profiles for iOS and Android.

Not ready yet:

- Microsoft Outlook mobile sign-in.
- Generic IMAP mobile password flow.
- Guaranteed background sync on iOS. iOS background execution is limited, so desktop scheduling remains more reliable.

## Apple vs iCloud

Apple Developer credentials are for signing, TestFlight, and App Store publishing. They are not an iCloud Calendar login.

For iPhone calendar sync, the app asks the phone for calendar permission and writes to calendars already enabled in iOS Settings. If the user has iCloud Calendar enabled, an existing iCloud calendar such as `Wellpass` or `Sport` can be used.

## Google Setup

Create a Google Cloud project for the mobile app:

1. Enable the Gmail API.
2. Enable the Google Calendar API.
3. Configure the OAuth consent screen.
4. Add the Gmail and Calendar scopes used by the app.
5. Create OAuth client IDs for iOS and Android.

Use these identifiers:

- iOS bundle ID: `com.mertcakir.wellpasssync`
- Android package name: `com.mertcakir.wellpasssync`
- Redirect scheme: `wellpasssync`

For Android, Google also needs the signing certificate SHA-1. If EAS manages credentials, get it with:

```bash
npx eas credentials -p android
```

Copy the example env file:

```bash
cd mobile
cp .env.example .env
```

Fill in:

```bash
EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID=
EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID=
EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID=
```

The web client ID is useful for development and Expo auth flows. The iOS and Android client IDs are required for real device builds.

Important: `https://www.googleapis.com/auth/gmail.readonly` is a restricted Gmail scope. For a public app, Google may require OAuth app verification and possibly additional review. Keep the app local-first, request the smallest scopes possible, and publish a privacy policy before submitting for verification.

Official references:

- [Expo AuthSession](https://docs.expo.dev/versions/latest/sdk/auth-session/)
- [Google OAuth 2.0 client types](https://developers.google.com/identity/protocols/oauth2)
- [Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Gmail messages list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)

## Run Locally

```bash
cd mobile
npm install
npm run test
npm run typecheck
npm run start
```

## Build Test Apps

Install and log in to EAS CLI:

```bash
npm install -g eas-cli
npx eas login
```

Configure the Expo project once:

```bash
cd mobile
npx eas build:configure
```

Build internal test apps:

```bash
npx eas build --platform android --profile preview
npx eas build --platform ios --profile preview
```

The current iOS preview profile builds for the simulator. For real iPhone testing, change the `preview.ios.simulator` value in `eas.json` or add a separate device profile.

## Production Builds

Build store-ready apps:

```bash
cd mobile
npx eas build --platform android --profile production
npx eas build --platform ios --profile production
```

Submit to stores:

```bash
npx eas submit --platform android --profile production
npx eas submit --platform ios --profile production
```

Official references:

- [Expo EAS Submit](https://docs.expo.dev/submit/introduction/)
- [Submit to app stores with Expo](https://docs.expo.dev/deploy/submit-to-app-stores/)
- [Apple App Store Connect](https://developer.apple.com/app-store-connect/)

## Release Checklist

Before App Store or Play Store submission:

1. Add real Google OAuth client IDs to `mobile/.env`.
2. Build and test on a physical iPhone and Android phone.
3. Verify Gmail sign-in, test run, and Sync now.
4. Verify events appear in the selected calendar with title, location, notes, and alerts.
5. Confirm cancellation emails remove matching events.
6. Prepare privacy policy and support URL.
7. Complete Google OAuth verification if required.
8. Submit iOS through App Store Connect or EAS Submit.
9. Submit Android through Play Console or EAS Submit.
