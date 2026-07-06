import { CalendarCheck, CircleCheck, Link, Mail, Play, RefreshCcw, Settings, Smartphone } from "lucide-react-native";
import { StatusBar } from "expo-status-bar";
import * as Google from "expo-auth-session/providers/google";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Alert, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";

import { appConfig, GOOGLE_SCOPES, hasGoogleCredentials } from "./src/config/appConfig";
import { runMobileSync } from "./src/core/mobileSync";
import type { CalendarProvider, EmailProvider, SyncLogEntry } from "./src/core/types";
import { ensureDeviceCalendar } from "./src/providers/deviceCalendar";
import { isGoogleTokenUsable, loadGoogleToken, saveGoogleToken, type StoredGoogleToken } from "./src/storage/secureTokens";

WebBrowser.maybeCompleteAuthSession();

const emailOptions: Array<{ value: EmailProvider; label: string; description: string }> = [
  { value: "gmail", label: "Gmail", description: "Sign in with Google to read Wellpass emails." },
  { value: "microsoft", label: "Outlook", description: "Microsoft mobile sign-in is planned after the Google release path." },
  { value: "imap", label: "Other email", description: "IMAP is supported on desktop; mobile password flow is planned." },
];

const calendarOptions: Array<{ value: CalendarProvider; label: string; description: string }> = [
  {
    value: "device",
    label: "Phone Calendar",
    description: "Writes to calendars already on this phone. On iPhone, this includes iCloud calendars.",
  },
  { value: "google", label: "Google Calendar", description: "Sign in with Google and choose or create a calendar." },
  { value: "outlook", label: "Outlook Calendar", description: "Microsoft mobile calendar sync is planned after Google." },
];

export default function App() {
  const [emailProvider, setEmailProvider] = useState<EmailProvider>("gmail");
  const [calendarProvider, setCalendarProvider] = useState<CalendarProvider>("device");
  const [calendarName, setCalendarName] = useState("Wellpass");
  const [googleToken, setGoogleToken] = useState<StoredGoogleToken | null>(null);
  const [busy, setBusy] = useState(false);
  const [logs, setLogs] = useState<SyncLogEntry[]>([
    { level: "info", message: "Choose accounts, then run a test before syncing." },
  ]);

  const [googleRequest, googleResponse, promptGoogleAuth] = Google.useAuthRequest(
    {
      androidClientId: appConfig.google.androidClientId,
      iosClientId: appConfig.google.iosClientId,
      webClientId: appConfig.google.webClientId,
      scopes: GOOGLE_SCOPES,
      selectAccount: true,
    },
    { scheme: "wellpasssync" },
  );

  useEffect(() => {
    void loadGoogleToken().then((token) => {
      if (isGoogleTokenUsable(token)) {
        setGoogleToken(token);
      }
    });
  }, []);

  useEffect(() => {
    if (!googleResponse) {
      return;
    }

    if (googleResponse.type === "success") {
      const auth = googleResponse.authentication;
      if (!auth?.accessToken) {
        appendLog({ level: "error", message: "Google sign-in finished without an access token." });
        return;
      }

      const token: StoredGoogleToken = {
        accessToken: auth.accessToken,
        issuedAt: auth.issuedAt,
        expiresIn: auth.expiresIn,
        refreshToken: auth.refreshToken,
        scope: auth.scope,
      };
      void saveGoogleToken(token).then(() => {
        setGoogleToken(token);
        appendLog({ level: "success", message: "Google connected." });
      });
    } else if (googleResponse.type === "error") {
      appendLog({ level: "error", message: "Google sign-in failed." });
    } else if (googleResponse.type === "cancel" || googleResponse.type === "dismiss") {
      appendLog({ level: "warning", message: "Google sign-in was cancelled." });
    }
  }, [googleResponse]);

  const selectedEmail = useMemo(() => emailOptions.find((option) => option.value === emailProvider)!, [emailProvider]);
  const selectedCalendar = useMemo(() => calendarOptions.find((option) => option.value === calendarProvider)!, [calendarProvider]);
  const googleConnected = isGoogleTokenUsable(googleToken);

  function appendLog(entry: SyncLogEntry) {
    setLogs((current) => [entry, ...current].slice(0, 40));
  }

  async function connect(kind: "email" | "calendar") {
    if ((kind === "email" && emailProvider === "gmail") || (kind === "calendar" && calendarProvider === "google")) {
      await connectGoogle();
      return;
    }

    if (kind === "calendar" && calendarProvider === "device") {
      await connectDeviceCalendar();
      return;
    }

    Alert.alert("Not ready on mobile yet", `${kind === "email" ? selectedEmail.label : selectedCalendar.label} works on desktop today. Mobile support is next.`);
  }

  async function connectGoogle() {
    if (!hasGoogleCredentials()) {
      Alert.alert("Google setup missing", "Add the Google OAuth client IDs to mobile/.env before signing in.");
      appendLog({ level: "error", message: "Google OAuth client IDs are not configured." });
      return;
    }
    if (!googleRequest) {
      appendLog({ level: "warning", message: "Google sign-in is still loading. Try again in a moment." });
      return;
    }

    try {
      await promptGoogleAuth();
    } catch (error) {
      appendLog({ level: "error", message: error instanceof Error ? error.message : "Google sign-in could not start." });
    }
  }

  async function connectDeviceCalendar() {
    setBusy(true);
    try {
      const calendar = await ensureDeviceCalendar(calendarName);
      appendLog({ level: "success", message: `Phone calendar ready: ${calendar.title}` });
    } catch (error) {
      appendLog({ level: "error", message: error instanceof Error ? error.message : "Calendar access failed." });
    } finally {
      setBusy(false);
    }
  }

  async function runSync(write: boolean) {
    if (!write) {
      await executeSync(false);
      return;
    }

    if (emailProvider !== "gmail") {
      Alert.alert("Email not ready", "Real mobile sync currently needs Gmail connected. Outlook and IMAP remain desktop paths for now.");
      return;
    }
    if (!googleConnected) {
      Alert.alert("Connect Gmail first", "Sign in with Google before writing calendar events.");
      return;
    }
    if (calendarProvider === "google" && !googleConnected) {
      Alert.alert("Connect Google Calendar first", "Sign in with Google before writing to Google Calendar.");
      return;
    }
    if (calendarProvider === "outlook") {
      Alert.alert("Outlook Calendar not ready", "Outlook Calendar works on desktop today. Mobile support is planned after the Google path.");
      return;
    }

    await executeSync(true);
  }

  async function executeSync(write: boolean) {
    setBusy(true);
    setLogs([{ level: "info", message: write ? "Sync started." : "Test run started." }]);
    try {
      const nextLogs = await runMobileSync({
        dryRun: !write,
        emailProvider,
        calendarProvider,
        calendarName,
        googleAccessToken: googleToken?.accessToken,
      });
      setLogs(nextLogs);
    } catch (error) {
      setLogs([{ level: "error", message: error instanceof Error ? error.message : "Sync failed." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={styles.headerIcon}>
            <Smartphone color="#ffffff" size={26} />
          </View>
          <View style={styles.headerText}>
            <Text style={styles.title}>Wellpass Calendar Sync</Text>
            <Text style={styles.subtitle}>iPhone and Android</Text>
          </View>
        </View>

        <StepCard number="1" title="Wellpass emails" icon={<Mail color="#0f766e" size={22} />} description="Choose the account where Wellpass emails arrive.">
          <SegmentedOptions options={emailOptions} value={emailProvider} onChange={setEmailProvider} />
          <Text style={styles.helper}>{selectedEmail.description}</Text>
          <ConnectionStatus connected={emailProvider === "gmail" && googleConnected} label={emailProvider === "gmail" ? "Google" : selectedEmail.label} />
          <PrimaryButton label="Connect email" icon={<CircleCheck color="#ffffff" size={18} />} disabled={busy} onPress={() => void connect("email")} />
        </StepCard>

        <StepCard number="2" title="Calendar" icon={<CalendarCheck color="#b91c1c" size={22} />} description="Choose where workout events should appear.">
          <SegmentedOptions options={calendarOptions} value={calendarProvider} onChange={setCalendarProvider} />
          <Text style={styles.helper}>{selectedCalendar.description}</Text>
          <View style={styles.calendarRow}>
            <Text style={styles.calendarLabel}>Calendar</Text>
            <View style={styles.calendarChoice}>
              <Pressable style={[styles.chip, calendarName === "Wellpass" && styles.chipSelected]} onPress={() => setCalendarName("Wellpass")}>
                <Text style={[styles.chipText, calendarName === "Wellpass" && styles.chipTextSelected]}>Wellpass</Text>
              </Pressable>
              <Pressable style={[styles.chip, calendarName === "Sport" && styles.chipSelected]} onPress={() => setCalendarName("Sport")}>
                <Text style={[styles.chipText, calendarName === "Sport" && styles.chipTextSelected]}>Sport</Text>
              </Pressable>
            </View>
          </View>
          <ConnectionStatus connected={calendarProvider === "device" || (calendarProvider === "google" && googleConnected)} label={selectedCalendar.label} />
          <PrimaryButton label="Connect calendar" icon={<CircleCheck color="#ffffff" size={18} />} disabled={busy} onPress={() => void connect("calendar")} />
        </StepCard>

        <StepCard number="3" title="Test and sync" icon={<Play color="#1d4ed8" size={22} />} description="Test run reads mail but does not change your calendar.">
          <View style={styles.actionRow}>
            <PrimaryButton label="Test run" icon={<RefreshCcw color="#ffffff" size={18} />} disabled={busy} onPress={() => void runSync(false)} />
            <SecondaryButton label="Sync now" icon={<Play color="#1f2937" size={18} />} disabled={busy} onPress={() => void runSync(true)} />
          </View>
        </StepCard>

        <View style={styles.logPanel}>
          <View style={styles.logHeader}>
            <Settings color="#374151" size={18} />
            <Text style={styles.logTitle}>Log</Text>
          </View>
          {logs.map((entry, index) => (
            <View key={`${entry.message}-${index}`} style={styles.logLine}>
              <View style={[styles.logDot, styles[`logDot_${entry.level}`]]} />
              <Text style={styles.logText}>{entry.message}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function StepCard({ number, title, icon, description, children }: { number: string; title: string; icon: ReactNode; description: string; children: ReactNode }) {
  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.stepBadge}>
          <Text style={styles.stepBadgeText}>{number}</Text>
        </View>
        {icon}
        <View style={styles.cardHeaderText}>
          <Text style={styles.cardTitle}>{title}</Text>
          <Text style={styles.cardDescription}>{description}</Text>
        </View>
      </View>
      {children}
    </View>
  );
}

function SegmentedOptions<T extends string>({ options, value, onChange }: { options: Array<{ value: T; label: string }>; value: T; onChange: (value: T) => void }) {
  return (
    <View style={styles.segmented}>
      {options.map((option) => {
        const selected = value === option.value;
        return (
          <Pressable key={option.value} style={[styles.segment, selected && styles.segmentSelected]} onPress={() => onChange(option.value)}>
            <Text style={[styles.segmentText, selected && styles.segmentTextSelected]}>{option.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function ConnectionStatus({ connected, label }: { connected: boolean; label: string }) {
  return (
    <View style={styles.statusRow}>
      <Link color={connected ? "#0f766e" : "#6b7280"} size={16} />
      <Text style={[styles.statusText, connected && styles.statusTextConnected]}>{connected ? `${label} ready` : `${label} not connected`}</Text>
    </View>
  );
}

function PrimaryButton({ label, icon, disabled, onPress }: { label: string; icon: ReactNode; disabled?: boolean; onPress: () => void }) {
  return (
    <Pressable style={[styles.primaryButton, disabled && styles.buttonDisabled]} disabled={disabled} onPress={onPress}>
      {icon}
      <Text style={styles.primaryButtonText}>{label}</Text>
    </Pressable>
  );
}

function SecondaryButton({ label, icon, disabled, onPress }: { label: string; icon: ReactNode; disabled?: boolean; onPress: () => void }) {
  return (
    <Pressable style={[styles.secondaryButton, disabled && styles.buttonDisabled]} disabled={disabled} onPress={onPress}>
      {icon}
      <Text style={styles.secondaryButtonText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#f5f7fb",
  },
  content: {
    gap: 14,
    padding: 18,
    paddingBottom: 34,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    marginBottom: 4,
  },
  headerIcon: {
    alignItems: "center",
    backgroundColor: "#0f766e",
    borderRadius: 8,
    height: 48,
    justifyContent: "center",
    width: 48,
  },
  headerText: {
    flex: 1,
  },
  title: {
    color: "#111827",
    fontSize: 24,
    fontWeight: "700",
  },
  subtitle: {
    color: "#4b5563",
    fontSize: 15,
    marginTop: 2,
  },
  card: {
    backgroundColor: "#ffffff",
    borderColor: "#d9e1ea",
    borderRadius: 8,
    borderWidth: 1,
    gap: 12,
    padding: 14,
  },
  cardHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
  },
  stepBadge: {
    alignItems: "center",
    backgroundColor: "#e6f4f1",
    borderRadius: 999,
    height: 28,
    justifyContent: "center",
    width: 28,
  },
  stepBadgeText: {
    color: "#0f766e",
    fontSize: 14,
    fontWeight: "700",
  },
  cardHeaderText: {
    flex: 1,
  },
  cardTitle: {
    color: "#111827",
    fontSize: 18,
    fontWeight: "700",
  },
  cardDescription: {
    color: "#4b5563",
    fontSize: 13,
    lineHeight: 18,
    marginTop: 2,
  },
  helper: {
    color: "#374151",
    fontSize: 14,
    lineHeight: 20,
  },
  segmented: {
    backgroundColor: "#eef2f7",
    borderRadius: 8,
    flexDirection: "row",
    gap: 4,
    padding: 4,
  },
  segment: {
    alignItems: "center",
    borderRadius: 6,
    flex: 1,
    justifyContent: "center",
    minHeight: 42,
    paddingHorizontal: 6,
  },
  segmentSelected: {
    backgroundColor: "#ffffff",
    shadowColor: "#111827",
    shadowOpacity: 0.08,
    shadowRadius: 5,
  },
  segmentText: {
    color: "#4b5563",
    fontSize: 12,
    fontWeight: "700",
    textAlign: "center",
  },
  segmentTextSelected: {
    color: "#111827",
  },
  statusRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  statusText: {
    color: "#6b7280",
    fontSize: 14,
    fontWeight: "600",
  },
  statusTextConnected: {
    color: "#0f766e",
  },
  calendarRow: {
    gap: 8,
  },
  calendarLabel: {
    color: "#111827",
    fontSize: 14,
    fontWeight: "700",
  },
  calendarChoice: {
    flexDirection: "row",
    gap: 8,
  },
  chip: {
    borderColor: "#cbd5e1",
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  chipSelected: {
    backgroundColor: "#fee2e2",
    borderColor: "#ef4444",
  },
  chipText: {
    color: "#374151",
    fontSize: 14,
    fontWeight: "700",
  },
  chipTextSelected: {
    color: "#991b1b",
  },
  actionRow: {
    flexDirection: "row",
    gap: 10,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#0f766e",
    borderRadius: 8,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 46,
    paddingHorizontal: 14,
  },
  primaryButtonText: {
    color: "#ffffff",
    fontSize: 15,
    fontWeight: "700",
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: "#e5e7eb",
    borderRadius: 8,
    flex: 1,
    flexDirection: "row",
    gap: 8,
    justifyContent: "center",
    minHeight: 46,
    paddingHorizontal: 14,
  },
  secondaryButtonText: {
    color: "#1f2937",
    fontSize: 15,
    fontWeight: "700",
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  logPanel: {
    backgroundColor: "#ffffff",
    borderColor: "#d9e1ea",
    borderRadius: 8,
    borderWidth: 1,
    gap: 10,
    padding: 14,
  },
  logHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
  },
  logTitle: {
    color: "#111827",
    fontSize: 17,
    fontWeight: "700",
  },
  logLine: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 8,
  },
  logDot: {
    borderRadius: 99,
    height: 8,
    marginTop: 6,
    width: 8,
  },
  logDot_info: {
    backgroundColor: "#2563eb",
  },
  logDot_success: {
    backgroundColor: "#0f766e",
  },
  logDot_warning: {
    backgroundColor: "#f59e0b",
  },
  logDot_error: {
    backgroundColor: "#dc2626",
  },
  logText: {
    color: "#374151",
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
});
