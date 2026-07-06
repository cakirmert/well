import { parseBookingEmail, sourceEmailFromRaw } from "../core/parser";
import type { BookingEvent, SourceEmail } from "../core/types";

declare const Buffer: { from(value: string, encoding: string): { toString(encoding: string): string } } | undefined;

const GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me";
const CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3";

interface GmailListResponse {
  messages?: Array<{ id: string; threadId?: string }>;
}

interface GmailMessageResponse {
  id: string;
  raw?: string;
}

interface GoogleCalendarListResponse {
  items?: Array<{ id: string; summary?: string; accessRole?: string }>;
}

interface GoogleCalendarResponse {
  id: string;
  summary?: string;
}

interface GoogleEventResponse {
  id: string;
}

export interface GoogleEmailOptions {
  accessToken: string;
  sender: string;
  maxResults?: number;
  searchDays?: number;
}

export async function listWellpassEmailsFromGmail({
  accessToken,
  sender,
  maxResults = 25,
  searchDays = 30,
}: GoogleEmailOptions): Promise<SourceEmail[]> {
  const safeSearchDays = Math.max(1, Math.round(searchDays));
  const query = `from:${sender} newer_than:${safeSearchDays}d`;
  const listUrl = `${GMAIL_BASE_URL}/messages?q=${encodeURIComponent(query)}&maxResults=${maxResults}`;
  const list = await fetchGoogleJson<GmailListResponse>(listUrl, accessToken);
  const messages = list.messages ?? [];

  const emails: SourceEmail[] = [];
  for (const message of messages) {
    const detail = await fetchGoogleJson<GmailMessageResponse>(
      `${GMAIL_BASE_URL}/messages/${encodeURIComponent(message.id)}?format=raw`,
      accessToken,
    );
    if (!detail.raw) {
      continue;
    }
    emails.push(sourceEmailFromRaw(base64UrlDecode(detail.raw)));
  }
  return emails;
}

export async function ensureGoogleCalendar(accessToken: string, calendarName: string): Promise<string> {
  const calendars = await fetchGoogleJson<GoogleCalendarListResponse>(`${CALENDAR_BASE_URL}/users/me/calendarList`, accessToken);
  const existing = (calendars.items ?? []).find((calendar) => calendar.summary?.toLowerCase() === calendarName.toLowerCase());
  if (existing?.id) {
    return existing.id;
  }

  const created = await fetchGoogleJson<GoogleCalendarResponse>(`${CALENDAR_BASE_URL}/calendars`, accessToken, {
    method: "POST",
    body: JSON.stringify({
      summary: calendarName,
      timeZone: "Europe/Berlin",
    }),
  });
  return created.id;
}

export async function syncGoogleCalendarEvent(
  accessToken: string,
  calendarId: string,
  event: BookingEvent,
): Promise<"created" | "updated" | "cancelled" | "skipped"> {
  if (event.status === "cancelled") {
    return deleteGoogleCalendarEvent(accessToken, calendarId, event);
  }
  if (!event.startAt) {
    return "skipped";
  }

  const eventId = googleEventId(event);
  const body = JSON.stringify(toGoogleEventPayload(event, eventId));
  const existing = await tryFetchGoogleJson<GoogleEventResponse>(
    `${CALENDAR_BASE_URL}/calendars/${encodeURIComponent(calendarId)}/events/${encodeURIComponent(eventId)}`,
    accessToken,
  );

  if (existing.ok) {
    await fetchGoogleJson<GoogleEventResponse>(
      `${CALENDAR_BASE_URL}/calendars/${encodeURIComponent(calendarId)}/events/${encodeURIComponent(eventId)}`,
      accessToken,
      { method: "PUT", body },
    );
    return "updated";
  }

  await fetchGoogleJson<GoogleEventResponse>(`${CALENDAR_BASE_URL}/calendars/${encodeURIComponent(calendarId)}/events`, accessToken, {
    method: "POST",
    body,
  });
  return "created";
}

export function parseGmailEmailsForPreview(emails: SourceEmail[], timezone = "Europe/Berlin"): BookingEvent[] {
  return emails.map((email) => parseBookingEmail(email, timezone)).filter((event): event is BookingEvent => Boolean(event));
}

async function deleteGoogleCalendarEvent(
  accessToken: string,
  calendarId: string,
  event: BookingEvent,
): Promise<"cancelled" | "skipped"> {
  const eventId = googleEventId(event);
  const response = await fetch(`${CALENDAR_BASE_URL}/calendars/${encodeURIComponent(calendarId)}/events/${encodeURIComponent(eventId)}`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
  if (response.status === 404 || response.status === 410) {
    return "skipped";
  }
  if (!response.ok) {
    throw new Error(await googleErrorMessage(response));
  }
  return "cancelled";
}

function toGoogleEventPayload(event: BookingEvent, eventId: string) {
  const endAt = event.endAt ?? event.startAt;
  return {
    id: eventId,
    summary: event.title,
    location: event.location ?? event.studio ?? undefined,
    description: event.notes || undefined,
    start: {
      dateTime: event.startAt,
      timeZone: event.timezone,
    },
    end: {
      dateTime: endAt,
      timeZone: event.timezone,
    },
    reminders: {
      useDefault: false,
      overrides: [
        { method: "popup", minutes: 60 },
        { method: "popup", minutes: 1440 },
      ],
    },
    extendedProperties: {
      private: {
        wellpassSync: "true",
        wellpassFingerprint: event.fingerprint,
        wellpassSourceMessageId: event.sourceMessageId,
      },
    },
  };
}

function googleEventId(event: BookingEvent): string {
  const hexOnly = event.fingerprint.toLowerCase().replace(/[^a-f0-9]/g, "");
  return `a${hexOnly.padEnd(8, "0").slice(0, 63)}`;
}

async function fetchGoogleJson<T>(url: string, accessToken: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...authHeaders(accessToken),
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(await googleErrorMessage(response));
  }
  return (await response.json()) as T;
}

async function tryFetchGoogleJson<T>(url: string, accessToken: string): Promise<{ ok: true; value: T } | { ok: false }> {
  const response = await fetch(url, { headers: authHeaders(accessToken) });
  if (response.status === 404 || response.status === 410) {
    return { ok: false };
  }
  if (!response.ok) {
    throw new Error(await googleErrorMessage(response));
  }
  return { ok: true, value: (await response.json()) as T };
}

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

async function googleErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `Google API request failed with HTTP ${response.status}`;
  }
  try {
    const payload = JSON.parse(text) as { error?: { message?: string } };
    return payload.error?.message ?? `Google API request failed with HTTP ${response.status}`;
  } catch {
    return text;
  }
}

export function base64UrlDecode(value: string): string {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  if (typeof globalThis.atob === "function") {
    const binary = globalThis.atob(base64);
    try {
      return decodeURIComponent(
        Array.from(binary)
          .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`)
          .join(""),
      );
    } catch {
      return binary;
    }
  }
  if (typeof Buffer !== "undefined") {
    return Buffer.from(base64, "base64").toString("utf8");
  }
  throw new Error("This device cannot decode Gmail messages because base64 decoding is unavailable.");
}
