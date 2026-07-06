export type BookingStatus = "confirmed" | "cancelled";

export type EmailProvider = "microsoft" | "gmail" | "imap";
export type CalendarProvider = "device" | "google" | "outlook";

export interface SourceEmail {
  messageId: string;
  subject: string;
  sender: string;
  bodyText: string;
  rawText: string;
}

export interface BookingEvent {
  sourceMessageId: string;
  sourceSubject: string;
  sourceSender: string;
  bookingId: string | null;
  title: string;
  studio: string | null;
  startAt: string | null;
  endAt: string | null;
  timezone: string;
  location: string | null;
  status: BookingStatus;
  fingerprint: string;
  calendarUid: string;
  notes: string;
}

export interface SyncLogEntry {
  level: "info" | "success" | "warning" | "error";
  message: string;
}
