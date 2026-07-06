import { CalendarCheck, CircleCheck, Mail, Play, RefreshCcw, Settings, Smartphone } from "lucide-react-native";
import { useMemo, useState } from "react";
import { Alert, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import { runSampleSync } from "./src/core/sampleSync";
import type { CalendarProvider, EmailProvider, SyncLogEntry } from "./src/core/types";

const emailOptions: Array<{ value: EmailProvider; label: string; description: string }> = [
  { value: "microsoft", label: "Outlook / Microsoft", description: "Use Microsoft Graph for Outlook.com or Microsoft 365." },
  { value: "gmail", label: "Gmail", description: "Use native Google sign-in for Gmail." },
  { value: "imap", label: "iCloud / IMAP", description: "Use email address plus provider app password." },
];

const calendarOptions: Array<{ value: CalendarProvider; label: string; description: string }> = [
  { value: "icloud", label: "iCloud Calendar", description: "Use Apple app-specific password and CalDAV." },
  { value: "google", label: "Google Calendar", description: "Use Google sign-in and Calendar API." },
  { value: "outlook", label: "Outlook Calendar", description: "Use Microsoft Graph calendar access." },
];

export default function App() {
  const [emailProvider, setEmailProvider] = useState<EmailProvider>("microsoft");
  const [calendarProvider, setCalendarProvider] = useState<CalendarProvider>("icloud");
  const [calendarName, setCalendarName] = useState("Wellpass");
  const [logs, setLogs] = useState<SyncLogEntry[]>([
    { level: "info", message: "Choose accounts, then run a test before syncing." },
  ]);

  const selectedEmail = useMemo(() => emailOptions.find((option) => option.value === emailProvider)!, [emailProvider]);
  const selectedCalendar = useMemo(() => calendarOptions.find((option) => option.value === calendarProvider)!, [calendarProvider]);

  function connect(kind: "email" | "calendar") {
    const label = kind === "email" ? selectedEmail.label : selectedCalendar.label;
    Alert.alert(
      "Connection setup",
      `${label} is selected. OAuth and secure password storage are scaffolded for the mobile app, but real provider credentials still need to be configured before public mobile release.`,
    );
  }

  function runTest(write: boolean) {
    setLogs(runSampleSync(write));
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
            <Text style={styles.subtitle}>iPhone and Android preview</Text>
          </View>
        </View>

        <StepCard
          number="1"
          title="Wellpass emails"
          icon={<Mail color="#0f766e" size={22} />}
          description="Choose the account where Wellpass emails arrive."
        >
          <SegmentedOptions options={emailOptions} value={emailProvider} onChange={setEmailProvider} />
          <Text style={styles.helper}>{selectedEmail.description}</Text>
          <PrimaryButton label="Connect email account" icon={<CircleCheck color="#ffffff" size={18} />} onPress={() => connect("email")} />
        </StepCard>

        <StepCard
          number="2"
          title="Calendar"
          icon={<CalendarCheck color="#b91c1c" size={22} />}
          description="Choose where workout events should appear."
        >
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
          <PrimaryButton label="Connect calendar account" icon={<CircleCheck color="#ffffff" size={18} />} onPress={() => connect("calendar")} />
        </StepCard>

        <StepCard
          number="3"
          title="Test and sync"
          icon={<Play color="#1d4ed8" size={22} />}
          description="Run a test first. Sync writes only after providers are connected."
        >
          <View style={styles.actionRow}>
            <PrimaryButton label="Test run" icon={<RefreshCcw color="#ffffff" size={18} />} onPress={() => runTest(false)} />
            <SecondaryButton label="Sync now" icon={<Play color="#1f2937" size={18} />} onPress={() => runTest(true)} />
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

function StepCard({
  number,
  title,
  icon,
  description,
  children,
}: {
  number: string;
  title: string;
  icon: React.ReactNode;
  description: string;
  children: React.ReactNode;
}) {
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

function SegmentedOptions<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
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

function PrimaryButton({ label, icon, onPress }: { label: string; icon: React.ReactNode; onPress: () => void }) {
  return (
    <Pressable style={styles.primaryButton} onPress={onPress}>
      {icon}
      <Text style={styles.primaryButtonText}>{label}</Text>
    </Pressable>
  );
}

function SecondaryButton({ label, icon, onPress }: { label: string; icon: React.ReactNode; onPress: () => void }) {
  return (
    <Pressable style={styles.secondaryButton} onPress={onPress}>
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
    fontSize: 14,
    marginTop: 2,
  },
  segmented: {
    borderColor: "#cad5e2",
    borderRadius: 8,
    borderWidth: 1,
    overflow: "hidden",
  },
  segment: {
    backgroundColor: "#ffffff",
    borderBottomColor: "#cad5e2",
    borderBottomWidth: 1,
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  segmentSelected: {
    backgroundColor: "#0f766e",
  },
  segmentText: {
    color: "#1f2937",
    fontSize: 15,
    fontWeight: "600",
  },
  segmentTextSelected: {
    color: "#ffffff",
  },
  helper: {
    color: "#374151",
    fontSize: 14,
    lineHeight: 20,
  },
  calendarRow: {
    gap: 8,
  },
  calendarLabel: {
    color: "#374151",
    fontSize: 14,
    fontWeight: "700",
  },
  calendarChoice: {
    flexDirection: "row",
    gap: 8,
  },
  chip: {
    borderColor: "#cad5e2",
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
    fontWeight: "700",
  },
  chipTextSelected: {
    color: "#b91c1c",
  },
  actionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#0f766e",
    borderRadius: 8,
    flexDirection: "row",
    gap: 8,
    minHeight: 46,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  primaryButtonText: {
    color: "#ffffff",
    fontSize: 15,
    fontWeight: "700",
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderColor: "#cad5e2",
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    minHeight: 46,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  secondaryButtonText: {
    color: "#1f2937",
    fontSize: 15,
    fontWeight: "700",
  },
  logPanel: {
    backgroundColor: "#ffffff",
    borderColor: "#d9e1ea",
    borderRadius: 8,
    borderWidth: 1,
    padding: 14,
  },
  logHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    marginBottom: 10,
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
    paddingVertical: 6,
  },
  logDot: {
    borderRadius: 999,
    height: 8,
    marginTop: 6,
    width: 8,
  },
  logDot_info: {
    backgroundColor: "#3b82f6",
  },
  logDot_success: {
    backgroundColor: "#16a34a",
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
