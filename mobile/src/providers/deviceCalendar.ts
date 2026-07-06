import * as Calendar from "expo-calendar";

import type { BookingEvent } from "../core/types";

const WELLPASS_MARKER_PREFIX = "wellpass-sync:";
const DEFAULT_ALARMS = [{ relativeOffset: -60 }, { relativeOffset: -1440 }];

export async function ensureDeviceCalendar(calendarName: string): Promise<Calendar.ExpoCalendar> {
  const permission = await Calendar.requestCalendarPermissions(false);
  if (permission.status !== "granted") {
    throw new Error("Calendar permission was not granted.");
  }

  const calendars = await Calendar.getCalendars(Calendar.EntityTypes.EVENT);
  const existing = calendars.find((calendar) => calendar.title === calendarName && calendar.allowsModifications);
  if (existing) {
    return existing;
  }

  const source = preferredSource(calendars);
  return Calendar.createCalendar({
    title: calendarName,
    name: calendarName,
    color: "#ef4444",
    entityType: Calendar.EntityTypes.EVENT,
    source,
    sourceId: source.id,
  });
}

export async function syncDeviceCalendarEvent(
  calendarName: string,
  event: BookingEvent,
): Promise<"created" | "updated" | "cancelled" | "skipped"> {
  const calendar = await ensureDeviceCalendar(calendarName);
  const existing = await findExistingEvent(calendar, event);

  if (event.status === "cancelled") {
    if (!existing) {
      return "skipped";
    }
    await existing.delete();
    return "cancelled";
  }

  if (!event.startAt) {
    return "skipped";
  }

  const eventData = toDeviceEvent(event);
  if (existing) {
    await existing.update(eventData);
    return "updated";
  }

  await calendar.createEvent(eventData);
  return "created";
}

async function findExistingEvent(calendar: Calendar.ExpoCalendar, event: BookingEvent): Promise<Calendar.ExpoCalendarEvent | null> {
  const [start, end] = searchWindow(event);
  const events = await calendar.listEvents(start, end);
  const marker = markerFor(event);
  return (
    events.find((candidate) => candidate.notes?.includes(marker)) ??
    events.find((candidate) => candidate.title === event.title && sameStart(candidate.startDate, event.startAt)) ??
    null
  );
}

function toDeviceEvent(event: BookingEvent): Parameters<Calendar.ExpoCalendar["createEvent"]>[0] {
  const startDate = new Date(event.startAt!);
  const endDate = event.endAt ? new Date(event.endAt) : new Date(startDate.getTime() + 60 * 60 * 1000);
  return {
    title: event.title,
    startDate,
    endDate,
    timeZone: event.timezone,
    endTimeZone: event.timezone,
    location: event.location ?? event.studio ?? null,
    notes: withMarker(event),
    alarms: DEFAULT_ALARMS,
    allDay: false,
  };
}

function searchWindow(event: BookingEvent): [Date, Date] {
  if (event.startAt) {
    const start = new Date(event.startAt);
    const end = new Date(event.endAt ?? event.startAt);
    start.setHours(start.getHours() - 2);
    end.setHours(end.getHours() + 2);
    return [start, end];
  }

  const start = new Date();
  const end = new Date();
  start.setDate(start.getDate() - 30);
  end.setDate(end.getDate() + 180);
  return [start, end];
}

function preferredSource(calendars: Calendar.ExpoCalendar[]): Calendar.Source {
  const preferredCalendar =
    calendars.find((calendar) => {
      const type = String(calendar.source?.type ?? "").toLowerCase();
      const name = String(calendar.source?.name ?? "").toLowerCase();
      return calendar.allowsModifications && (name.includes("icloud") || type.includes("caldav") || type.includes("mobileme"));
    }) ??
    calendars.find((calendar) => calendar.allowsModifications && calendar.source) ??
    null;

  if (preferredCalendar?.source) {
    return preferredCalendar.source;
  }

  return {
    type: Calendar.SourceType.LOCAL,
    name: "Wellpass Calendar Sync",
    isLocalAccount: true,
  };
}

function markerFor(event: BookingEvent): string {
  return `${WELLPASS_MARKER_PREFIX}${event.fingerprint}`;
}

function withMarker(event: BookingEvent): string {
  return [event.notes, markerFor(event)].filter(Boolean).join("\n");
}

function sameStart(value: string | Date, expected: string | null): boolean {
  if (!expected) {
    return false;
  }
  return Math.abs(new Date(value).getTime() - new Date(expected).getTime()) < 60_000;
}
