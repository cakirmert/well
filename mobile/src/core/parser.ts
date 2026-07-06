import type { BookingEvent, SourceEmail } from "./types";

const CANCEL_WORDS = [
  "cancelled",
  "canceled",
  "cancellation",
  "cancelation",
  "storniert",
  "stornierung",
  "abgesagt",
  "abmeldung",
];

const MONTHS: Record<string, number> = {
  january: 1,
  jan: 1,
  february: 2,
  feb: 2,
  march: 3,
  mar: 3,
  april: 4,
  apr: 4,
  may: 5,
  june: 6,
  jun: 6,
  july: 7,
  jul: 7,
  august: 8,
  aug: 8,
  september: 9,
  sep: 9,
  october: 10,
  oct: 10,
  november: 11,
  nov: 11,
  december: 12,
  dec: 12,
  januar: 1,
  februar: 2,
  maerz: 3,
  marz: 3,
  mai: 5,
  juni: 6,
  juli: 7,
  oktober: 10,
  okt: 10,
  dezember: 12,
  dez: 12,
};

export function sourceEmailFromRaw(rawText: string): SourceEmail {
  const normalized = rawText.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const [headerText, ...bodyParts] = normalized.split(/\n\n/);
  const headers = parseHeaders(headerText ?? "");
  const subject = headers.subject ?? "";
  const sender = headers.from ?? "";
  const messageId = headers["message-id"] ?? `missing-message-id-${hashText(normalized).slice(0, 16)}`;

  return {
    messageId,
    subject,
    sender,
    bodyText: bodyParts.join("\n\n").trim(),
    rawText,
  };
}

export function parseBookingEmail(source: SourceEmail, timezone = "Europe/Berlin"): BookingEvent | null {
  const text = normalizeText(`${source.subject}\n${source.bodyText}`);
  const lower = text.toLowerCase();
  if (lower.includes("missed session") || lower.includes("no-show notice")) {
    return null;
  }

  const fields = extractFields(text);
  const subjectParts = inferTitleAndStudio(source.subject);
  const status = CANCEL_WORDS.some((word) => lower.includes(word)) ? "cancelled" : "confirmed";
  const cancellationParts = inferCancellationTitleAndStudio(text);

  const title = fields.title ?? cancellationParts.title ?? subjectParts.title;
  const studio = fields.studio ?? cancellationParts.studio ?? subjectParts.studio ?? senderDisplayName(source.sender);
  const dateParts = findDateParts(text);
  const timeRange = findTimeRange(text);
  const singleTime = timeRange ? null : findSingleTime(text);
  const durationMinutes = findDurationMinutes(text) ?? 60;
  const startAt = dateParts && (timeRange || singleTime) ? buildIso(dateParts, timeRange?.start ?? singleTime!, timezone) : null;
  const endAt =
    dateParts && timeRange
      ? buildIso(dateParts, timeRange.end, timezone)
      : startAt
        ? addMinutes(startAt, durationMinutes)
        : null;

  if (!title && !fields.bookingId) {
    return null;
  }
  if (status === "confirmed" && !startAt) {
    return null;
  }

  const eventTitle = title ?? "Wellpass booking";
  const eventFingerprint = buildFingerprint(fields.bookingId, eventTitle, studio, startAt);
  const notes = fields.trainer ? `Trainer: ${fields.trainer}` : "";

  return {
    sourceMessageId: source.messageId,
    sourceSubject: source.subject,
    sourceSender: source.sender,
    bookingId: fields.bookingId ?? null,
    title: eventTitle,
    studio: studio ?? null,
    startAt,
    endAt,
    timezone,
    location: fields.location ?? null,
    status,
    fingerprint: eventFingerprint,
    calendarUid: `wellpass-${eventFingerprint}@local`,
    notes,
  };
}

function parseHeaders(headerText: string): Record<string, string> {
  const headers: Record<string, string> = {};
  let current = "";
  for (const line of headerText.split("\n")) {
    if (/^\s/.test(line) && current) {
      headers[current] = `${headers[current]} ${line.trim()}`;
      continue;
    }
    const match = /^([^:]+):\s*(.*)$/.exec(line);
    if (!match) {
      continue;
    }
    const headerName = match[1];
    const headerValue = match[2];
    if (!headerName || headerValue === undefined) {
      continue;
    }
    current = headerName.toLowerCase();
    headers[current] = headerValue.trim();
  }
  return headers;
}

function normalizeText(value: string): string {
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
}

function extractFields(text: string) {
  const fields: {
    bookingId?: string;
    title?: string;
    studio?: string;
    location?: string;
    trainer?: string;
  } = {};
  for (const line of text.split("\n").map((part) => part.trim()).filter(Boolean)) {
    const match = /^([^:|-]+)\s*[:|-]\s*(.+)$/.exec(line);
    if (!match) {
      continue;
    }
    const label = match[1];
    const rawValue = match[2];
    if (!label || rawValue === undefined) {
      continue;
    }
    const key = normalizeKey(label);
    const value = cleanValue(rawValue);
    if (!value) {
      continue;
    }
    if (["booking id", "booking-id", "reservation id", "buchungsnummer", "buchungscode"].includes(key)) {
      fields.bookingId ??= value;
    } else if (["booked", "class", "course", "event", "workout", "training", "kurs", "termin"].includes(key)) {
      fields.title ??= value;
    } else if (["studio", "provider", "partner", "club", "anbieter"].includes(key)) {
      fields.studio ??= value;
    } else if (["location", "address", "adresse", "ort"].includes(key)) {
      fields.location ??= value;
    } else if (key === "trainer") {
      fields.trainer ??= value;
    }
  }
  return fields;
}

function inferTitleAndStudio(subject: string): { title?: string; studio?: string } {
  let cleaned = subject.replace(/^(re|fwd?)\s*:\s*/i, "").trim();
  cleaned = cleaned
    .replace(
      /\b(booking confirmation|booking confirmed|confirmed|reservation confirmed|your booking|reminder|updated|late cancellation|cancellation confirmed|cancellation|cancelled|canceled|stornierung|storniert)\b/gi,
      "",
    )
    .replace(/^[\s:|-]+/, "")
    .trim();
  const match = /^(.+?)\s+(?:at|bei|in)\s+(.+)$/.exec(cleaned);
  if (match) {
    return { title: cleanValue(match[1] ?? ""), studio: cleanValue(match[2] ?? "") };
  }
  return { title: cleanValue(cleaned) || undefined };
}

function inferCancellationTitleAndStudio(text: string): { title?: string; studio?: string } {
  const match = /successfully cancel(?:ed|led) your\s+(.+?)\s+session at\s+(.+?)\s+on\b/i.exec(text);
  if (!match) {
    return {};
  }
  return { title: cleanValue(match[1] ?? ""), studio: cleanValue(match[2] ?? "") };
}

function senderDisplayName(sender: string): string | undefined {
  const match = /^"?([^"<]+)"?\s*</.exec(sender);
  const value = cleanValue(match?.[1] ?? sender.split("@")[0] ?? "");
  return value || undefined;
}

function findDateParts(text: string): { year: number; month: number; day: number } | null {
  const compact = foldGerman(text.toLowerCase());
  const iso = /\b(20\d{2})-(\d{1,2})-(\d{1,2})\b/.exec(compact);
  if (iso) {
    return { year: Number(iso[1]!), month: Number(iso[2]!), day: Number(iso[3]!) };
  }
  const numeric = /\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b/.exec(compact);
  if (numeric) {
    const rawYear = Number(numeric[3]!);
    const year = rawYear < 100 ? rawYear + 2000 : rawYear;
    return { year, month: Number(numeric[2]!), day: Number(numeric[1]!) };
  }
  const monthNames = Object.keys(MONTHS).sort((a, b) => b.length - a.length).join("|");
  const german = new RegExp(`\\b(\\d{1,2})\\.?\\s*(${monthNames})\\s*(20\\d{2})\\b`).exec(compact);
  if (german) {
    return { year: Number(german[3]!), month: MONTHS[german[2]!]!, day: Number(german[1]!) };
  }
  const english = new RegExp(`\\b(${monthNames})\\s+(\\d{1,2})(?:st|nd|rd|th)?[,]?\\s+(20\\d{2})\\b`).exec(compact);
  if (english) {
    return { year: Number(english[3]!), month: MONTHS[english[1]!]!, day: Number(english[2]!) };
  }
  return null;
}

function findTimeRange(text: string): { start: TimeParts; end: TimeParts } | null {
  const match =
    /\b([0-2]?\d)[:.]([0-5]\d)\s*(am|pm)?\s*(?:uhr)?\s*(?:-|bis|to|until)\s*([0-2]?\d)[:.]([0-5]\d)\s*(am|pm)?\s*(?:uhr)?\b/i.exec(
      text,
    );
  if (!match) {
    return null;
  }
  return {
    start: { hour: hourWithAmpm(match[1]!, match[3]), minute: Number(match[2]!) },
    end: { hour: hourWithAmpm(match[4]!, match[6]), minute: Number(match[5]!) },
  };
}

function findSingleTime(text: string): TimeParts | null {
  const match = /\b(?:um|at|beginnt(?: um)?|starts?(?: at)?|von)?\s*([0-2]?\d)[:.]([0-5]\d)\s*(am|pm)?\s*(?:uhr)?\b/i.exec(text);
  if (!match) {
    return null;
  }
  return { hour: hourWithAmpm(match[1]!, match[3]), minute: Number(match[2]!) };
}

function findDurationMinutes(text: string): number | null {
  const hours = /\b(\d+(?:[.,]\d+)?)\s*(?:h|hr|hrs|hour|hours|stunde|stunden)\b/i.exec(text);
  if (hours) {
    const minutes = Math.round(Number(hours[1]!.replace(",", ".")) * 60);
    return minutes >= 15 && minutes <= 240 ? minutes : null;
  }
  const minutes = /\b(\d{2,3})\s*(?:min|minute|minutes|minuten)\b/i.exec(text);
  if (!minutes) {
    return null;
  }
  const value = Number(minutes[1]!);
  return value >= 15 && value <= 240 ? value : null;
}

interface TimeParts {
  hour: number;
  minute: number;
}

function buildIso(date: { year: number; month: number; day: number }, time: TimeParts, timezone: string): string {
  const offset = timezone === "Europe/Berlin" ? "+02:00" : "";
  return `${date.year}-${pad(date.month)}-${pad(date.day)}T${pad(time.hour)}:${pad(time.minute)}:00${offset}`;
}

function addMinutes(iso: string, minutes: number): string {
  const [datePart, timeWithOffset = "00:00:00"] = iso.split("T");
  const [timePart = "00:00:00", offset = ""] = timeWithOffset.split(/(?=[+-]\d\d:\d\d$)/);
  const [hour = 0, minute = 0] = timePart.split(":").map(Number);
  const date = new Date(`${datePart}T00:00:00Z`);
  date.setUTCHours(hour, minute + minutes, 0, 0);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:00${offset}`;
}

function hourWithAmpm(hour: string | undefined, ampm: string | undefined): number {
  const value = Number(hour);
  if (!ampm) {
    return value;
  }
  const marker = ampm.toLowerCase();
  if (marker === "am") {
    return value === 12 ? 0 : value;
  }
  return value === 12 ? value : value + 12;
}

function buildFingerprint(bookingId: string | undefined, title: string, studio: string | null | undefined, startAt: string | null): string {
  const basis = bookingId ? `booking-id:${slug(bookingId)}` : `${slug(title)}|${slug(studio ?? "")}|${startAt ?? "unknown-start"}`;
  return hashText(basis).slice(0, 32);
}

function hashText(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0").repeat(4);
}

function normalizeKey(value: string): string {
  return foldGerman(value.trim().toLowerCase());
}

function slug(value: string): string {
  return foldGerman(value.toLowerCase()).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function foldGerman(value: string): string {
  return value.replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss");
}

function cleanValue(value: string | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").replace(/^[^\w(]+/u, "").replace(/[\s:|\-]+$/g, "").trim();
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}
