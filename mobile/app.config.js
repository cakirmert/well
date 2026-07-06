const googleIosClientId = process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID;
const googleAndroidClientId = process.env.EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID;
const googleWebClientId = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;
const microsoftClientId = process.env.EXPO_PUBLIC_MICROSOFT_CLIENT_ID;
const microsoftTenant = process.env.EXPO_PUBLIC_MICROSOFT_TENANT ?? "consumers";

module.exports = {
  expo: {
    name: "Wellpass Calendar Sync",
    slug: "wellpass-calendar-sync",
    scheme: "wellpasssync",
    version: "0.1.0",
    orientation: "portrait",
    userInterfaceStyle: "automatic",
    assetBundlePatterns: ["**/*"],
    ios: {
      supportsTablet: true,
      bundleIdentifier: "com.mertcakir.wellpasssync",
      infoPlist: {
        NSCalendarsUsageDescription: "Wellpass Calendar Sync needs calendar access to add and update workout bookings.",
        NSCalendarsFullAccessUsageDescription: "Wellpass Calendar Sync needs full calendar access to update or cancel existing workout bookings.",
        NSCalendarsWriteOnlyAccessUsageDescription: "Wellpass Calendar Sync needs calendar access to add workout bookings.",
      },
    },
    android: {
      package: "com.mertcakir.wellpasssync",
      permissions: ["READ_CALENDAR", "WRITE_CALENDAR"],
    },
    plugins: ["expo-calendar", "expo-secure-store"],
    extra: {
      defaultTimezone: "Europe/Berlin",
      googleIosClientId,
      googleAndroidClientId,
      googleWebClientId,
      microsoftClientId,
      microsoftTenant,
    },
  },
};
