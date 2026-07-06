declare const process: { env?: Record<string, string | undefined> } | undefined;

const env = typeof process !== "undefined" && process?.env ? process.env : {};

function optionalEnv(name: string): string | undefined {
  const value = env[name]?.trim();
  return value ? value : undefined;
}

export const GOOGLE_SCOPES = [
  "openid",
  "profile",
  "email",
  "https://www.googleapis.com/auth/gmail.readonly",
  "https://www.googleapis.com/auth/calendar",
];

export const appConfig = {
  defaultTimezone: optionalEnv("EXPO_PUBLIC_DEFAULT_TIMEZONE") ?? "Europe/Berlin",
  defaultSender: optionalEnv("EXPO_PUBLIC_WELLPASS_SENDER") ?? "noreply-de@egym-wellpass.com",
  defaultSearchDays: Number(optionalEnv("EXPO_PUBLIC_SEARCH_DAYS") ?? "30"),
  google: {
    iosClientId: optionalEnv("EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID"),
    androidClientId: optionalEnv("EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID"),
    webClientId: optionalEnv("EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID"),
  },
  microsoft: {
    clientId: optionalEnv("EXPO_PUBLIC_MICROSOFT_CLIENT_ID"),
    tenant: optionalEnv("EXPO_PUBLIC_MICROSOFT_TENANT") ?? "consumers",
  },
};

export function hasGoogleCredentials(): boolean {
  return Boolean(appConfig.google.iosClientId || appConfig.google.androidClientId || appConfig.google.webClientId);
}
