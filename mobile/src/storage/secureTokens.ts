import * as SecureStore from "expo-secure-store";

const GOOGLE_TOKEN_KEY = "wellpass.google.token";

export interface StoredGoogleToken {
  accessToken: string;
  issuedAt: number;
  expiresIn?: number;
  refreshToken?: string;
  scope?: string;
}

export async function saveGoogleToken(token: StoredGoogleToken): Promise<void> {
  await SecureStore.setItemAsync(GOOGLE_TOKEN_KEY, JSON.stringify(token));
}

export async function loadGoogleToken(): Promise<StoredGoogleToken | null> {
  const raw = await SecureStore.getItemAsync(GOOGLE_TOKEN_KEY);
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<StoredGoogleToken>;
    if (typeof parsed.accessToken !== "string" || !parsed.accessToken) {
      return null;
    }
    return {
      accessToken: parsed.accessToken,
      issuedAt: typeof parsed.issuedAt === "number" ? parsed.issuedAt : Math.floor(Date.now() / 1000),
      expiresIn: parsed.expiresIn,
      refreshToken: parsed.refreshToken,
      scope: parsed.scope,
    };
  } catch {
    await clearGoogleToken();
    return null;
  }
}

export async function clearGoogleToken(): Promise<void> {
  await SecureStore.deleteItemAsync(GOOGLE_TOKEN_KEY);
}

export function isGoogleTokenUsable(token: StoredGoogleToken | null): boolean {
  if (!token) {
    return false;
  }
  if (!token.expiresIn) {
    return true;
  }
  const now = Math.floor(Date.now() / 1000);
  return token.issuedAt + token.expiresIn - 300 > now;
}
