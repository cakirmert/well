import AsyncStorage from "@react-native-async-storage/async-storage";

const PROCESSED_KEY = "wellpass.processed.message-fingerprints";
const MAX_PROCESSED = 500;

export async function loadProcessedFingerprints(): Promise<Set<string>> {
  const raw = await AsyncStorage.getItem(PROCESSED_KEY);
  if (!raw) {
    return new Set();
  }

  try {
    const values = JSON.parse(raw);
    return Array.isArray(values) ? new Set(values.filter((value): value is string => typeof value === "string")) : new Set();
  } catch {
    await AsyncStorage.removeItem(PROCESSED_KEY);
    return new Set();
  }
}

export async function markProcessedFingerprint(fingerprint: string): Promise<void> {
  const processed = await loadProcessedFingerprints();
  processed.add(fingerprint);
  const trimmed = Array.from(processed).slice(-MAX_PROCESSED);
  await AsyncStorage.setItem(PROCESSED_KEY, JSON.stringify(trimmed));
}

export async function clearProcessedFingerprints(): Promise<void> {
  await AsyncStorage.removeItem(PROCESSED_KEY);
}
