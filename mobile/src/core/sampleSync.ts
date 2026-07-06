import { sampleEmails } from "../fixtures/sampleEmails";
import { parseBookingEmail, sourceEmailFromRaw } from "./parser";
import type { SyncLogEntry } from "./types";

export function runSampleSync(write: boolean): SyncLogEntry[] {
  const logs: SyncLogEntry[] = [
    { level: "info", message: `Checked ${sampleEmails.length} sample Wellpass email(s).` },
  ];

  for (const rawEmail of sampleEmails) {
    const source = sourceEmailFromRaw(rawEmail);
    const event = parseBookingEmail(source);
    if (!event) {
      logs.push({ level: "warning", message: `Skipped an email I could not understand: ${source.subject}` });
      continue;
    }
    if (event.status === "cancelled") {
      logs.push({ level: write ? "success" : "info", message: `${write ? "Would remove" : "Would remove"}: ${event.title}` });
      continue;
    }
    logs.push({ level: write ? "success" : "info", message: `${write ? "Would add" : "Would add"}: ${event.title} at ${event.startAt}` });
  }

  logs.push({
    level: "info",
    message: write
      ? "Cloud calendar writes are not enabled in this mobile preview yet."
      : "Test run only. Your calendar was not changed.",
  });
  return logs;
}

export async function runSampleSyncAsync(write: boolean): Promise<SyncLogEntry[]> {
  return runSampleSync(write);
}
