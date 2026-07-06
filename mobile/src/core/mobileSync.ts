import { sampleEmails } from "../fixtures/sampleEmails";
import { appConfig } from "../config/appConfig";
import { ensureGoogleCalendar, listWellpassEmailsFromGmail, syncGoogleCalendarEvent } from "../providers/googleApi";
import { syncDeviceCalendarEvent } from "../providers/deviceCalendar";
import { loadProcessedFingerprints, markProcessedFingerprint } from "../storage/syncState";
import { parseBookingEmail, sourceEmailFromRaw } from "./parser";
import type { CalendarProvider, EmailProvider, SourceEmail, SyncLogEntry } from "./types";

export interface MobileSyncOptions {
  dryRun: boolean;
  emailProvider: EmailProvider;
  calendarProvider: CalendarProvider;
  calendarName: string;
  googleAccessToken?: string | null;
  searchDays?: number;
  maxResults?: number;
}

export async function runMobileSync(options: MobileSyncOptions): Promise<SyncLogEntry[]> {
  const logs: SyncLogEntry[] = [];
  validateWriteOptions(options);
  const emails = await loadEmails(options, logs);
  const processed = options.dryRun ? new Set<string>() : await loadProcessedFingerprints();

  logs.push({ level: "info", message: `Checked ${emails.length} Wellpass email(s).` });

  let created = 0;
  let updated = 0;
  let cancelled = 0;
  let skipped = 0;
  let ignored = 0;

  const googleCalendarId =
    !options.dryRun && options.calendarProvider === "google" && options.googleAccessToken
      ? await ensureGoogleCalendar(options.googleAccessToken, options.calendarName)
      : null;

  for (const source of emails) {
    const event = parseBookingEmail(source, appConfig.defaultTimezone);
    if (!event) {
      ignored += 1;
      logs.push({ level: "warning", message: `Ignored an email I could not understand: ${source.subject || "(no subject)"}` });
      continue;
    }

    const processedKey = `${source.messageId}:${event.status}:${event.fingerprint}`;
    if (!options.dryRun && processed.has(processedKey)) {
      skipped += 1;
      logs.push({ level: "info", message: `Skipped already processed email: ${event.title}` });
      continue;
    }

    if (options.dryRun) {
      logs.push({ level: "info", message: `${event.status === "cancelled" ? "Would cancel" : "Would add or update"}: ${event.title}` });
      continue;
    }

    const result = await writeEvent(options, event, googleCalendarId);
    if (result === "created") {
      created += 1;
      logs.push({ level: "success", message: `Created: ${event.title}` });
    } else if (result === "updated") {
      updated += 1;
      logs.push({ level: "success", message: `Updated: ${event.title}` });
    } else if (result === "cancelled") {
      cancelled += 1;
      logs.push({ level: "success", message: `Cancelled: ${event.title}` });
    } else {
      skipped += 1;
      logs.push({ level: "warning", message: `Skipped: ${event.title}` });
    }

    if (result !== "skipped") {
      await markProcessedFingerprint(processedKey);
      processed.add(processedKey);
    }
  }

  logs.push({
    level: "info",
    message: options.dryRun
      ? "Test run only. Your calendar was not changed."
      : `Done. Created ${created}, updated ${updated}, cancelled ${cancelled}, skipped ${skipped}, ignored ${ignored}.`,
  });
  return logs;
}

function validateWriteOptions(options: MobileSyncOptions): void {
  if (options.dryRun) {
    return;
  }
  if (options.emailProvider !== "gmail") {
    throw new Error("Real mobile sync currently needs Gmail. Outlook and IMAP work in the desktop app.");
  }
  if (!options.googleAccessToken) {
    throw new Error("Connect Google before syncing real calendar changes.");
  }
  if (options.calendarProvider === "outlook") {
    throw new Error("Outlook Calendar mobile sync is not connected yet.");
  }
}

async function loadEmails(options: MobileSyncOptions, logs: SyncLogEntry[]): Promise<SourceEmail[]> {
  if (options.emailProvider === "gmail" && options.googleAccessToken) {
    return listWellpassEmailsFromGmail({
      accessToken: options.googleAccessToken,
      sender: appConfig.defaultSender,
      searchDays: options.searchDays ?? appConfig.defaultSearchDays,
      maxResults: options.maxResults ?? 25,
    });
  }

  if (options.emailProvider !== "gmail") {
    logs.push({
      level: "warning",
      message: "This mobile email provider is not connected yet. Showing sample emails instead.",
    });
  } else {
    logs.push({
      level: "warning",
      message: "Gmail is not connected yet. Showing sample emails instead.",
    });
  }
  return sampleEmails.map((rawEmail) => sourceEmailFromRaw(rawEmail));
}

async function writeEvent(
  options: MobileSyncOptions,
  event: NonNullable<ReturnType<typeof parseBookingEmail>>,
  googleCalendarId: string | null,
): Promise<"created" | "updated" | "cancelled" | "skipped"> {
  if (options.calendarProvider === "device") {
    return syncDeviceCalendarEvent(options.calendarName, event);
  }

  if (options.calendarProvider === "google" && options.googleAccessToken && googleCalendarId) {
    return syncGoogleCalendarEvent(options.googleAccessToken, googleCalendarId, event);
  }

  return "skipped";
}
