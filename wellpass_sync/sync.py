from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from .config import AppConfig
from .calendar import make_calendar_writer, row_to_event
from .email_source import load_imap_emails, load_outlook_com_emails, load_sample_emails, sorted_messages
from .graph_mail import load_graph_emails
from .models import SourceEmail
from .parser import parse_booking_email
from .state import SyncState


@dataclass(frozen=True)
class SyncOptions:
    source: str = "auto"
    sample_dir: Path = Path("samples")
    dry_run: bool = True
    reprocess: bool = False
    limit: int | None = None
    force_ics: bool = False
    on_date: date | None = None
    from_date: date | None = None
    to_date: date | None = None
    sender_contains: str | None = None


@dataclass
class SyncSummary:
    scanned: int = 0
    parsed: int = 0
    created: int = 0
    updated: int = 0
    cancelled: int = 0
    skipped: int = 0
    ignored: int = 0
    errors: int = 0


def run_sync(config: AppConfig, options: SyncOptions) -> SyncSummary:
    summary = SyncSummary()
    messages = _load_messages(config, options)
    if options.sender_contains and _resolved_source(config, options) != "graph":
        needle = options.sender_contains.lower()
        messages = [message for message in messages if needle in message.sender.lower()]
    if options.limit:
        messages = messages[: options.limit]

    print(f"Loaded {len(messages)} candidate email(s) from {options.source}.")
    if options.dry_run:
        print("Dry run: no SQLite state or calendar writes will be performed.")
    if config.reminder_minutes:
        reminders = ", ".join(_format_reminder(minutes) for minutes in sorted(set(config.reminder_minutes), reverse=True))
        print(f"Calendar reminders: {reminders} before each event.")

    calendar = None if options.dry_run else make_calendar_writer(config, force_ics=options.force_ics)
    planned_bookings = {}
    known_locations: dict[str, str] = {}

    with SyncState(config.database_path, writable=not options.dry_run) as state:
        for source in sorted_messages(messages):
            summary.scanned += 1
            try:
                if not options.reprocess and state.has_processed_message(source):
                    summary.skipped += 1
                    print(f"SKIP already processed: {source.subject}")
                    continue

                event = parse_booking_email(source, config.timezone)
                if event is None:
                    summary.ignored += 1
                    print(f"IGNORE could not parse booking fields: {source.subject}")
                    if not options.dry_run:
                        state.record_message(source, None, "ignored")
                    continue

                event = _apply_known_location(event, known_locations)
                if event.studio and event.location and _is_rich_location(event.location):
                    known_locations[event.studio.lower()] = event.location

                summary.parsed += 1
                if not _event_in_date_scope(event, options):
                    summary.skipped += 1
                    if options.on_date:
                        print(f"SKIP outside {options.on_date}: {event.title} at {_when(event)}")
                    continue
                if event.is_cancelled:
                    _handle_cancellation(source, event, state, calendar, options, summary, planned_bookings)
                else:
                    _handle_booking(source, event, state, calendar, options, summary, planned_bookings)
            except Exception as exc:
                summary.errors += 1
                print(f"ERROR {source.subject}: {exc}")

    print(
        "Summary: "
        f"scanned={summary.scanned} parsed={summary.parsed} created={summary.created} "
        f"updated={summary.updated} cancelled={summary.cancelled} skipped={summary.skipped} "
        f"ignored={summary.ignored} errors={summary.errors}"
    )
    return summary


def _load_messages(config: AppConfig, options: SyncOptions) -> list[SourceEmail]:
    source = _resolved_source(config, options)
    if source == "samples":
        return load_sample_emails(options.sample_dir)
    if source == "imap":
        return load_imap_emails(config)
    if source == "outlook":
        return load_outlook_com_emails(config)
    if source == "graph":
        return load_graph_emails(
            config,
            sender_contains=options.sender_contains or _default_sender_hint(config),
            max_messages=options.limit,
        )
    if source == "gmail_oauth":
        from .gmail_mail import load_gmail_emails

        return load_gmail_emails(
            config,
            sender_contains=options.sender_contains or _default_sender_hint(config),
            max_messages=options.limit,
        )
    raise ValueError(f"Unsupported email source {source!r}")


def _default_sender_hint(config: AppConfig) -> str | None:
    return config.email_sender_hints[0] if config.email_sender_hints else None


def _resolved_source(config: AppConfig, options: SyncOptions) -> str:
    if options.source == "auto":
        return config.email_provider
    return options.source


def _handle_booking(
    source: SourceEmail,
    event,
    state: SyncState,
    calendar,
    options: SyncOptions,
    summary: SyncSummary,
    planned_bookings: dict[str, object],
) -> None:
    existing = state.get_booking(event.fingerprint)
    planned_existing = planned_bookings.get(event.fingerprint)
    changed = state.event_changed(existing, event)
    action = "created" if existing is None and planned_existing is None else "updated"

    if not changed:
        summary.skipped += 1
        print(f"SKIP unchanged: {event.title} at {_when(event)}")
        if not options.dry_run:
            state.record_message(source, event, "skipped")
        return

    if options.dry_run:
        verb = "create" if action == "created" else "update"
        print(f"DRY-RUN would {verb}: {event.title} at {_when(event)}")
        planned_bookings[event.fingerprint] = event
        return

    result = calendar.upsert_event(event, existing_href=existing["calendar_href"] if existing else None)
    state.upsert_booking(event, result.href)
    state.record_message(source, event, result.action)

    if existing is None:
        summary.created += 1
        printed_action = "CREATED"
    else:
        summary.updated += 1
        printed_action = "UPDATED"
    print(f"{printed_action}: {event.title} at {_when(event)}")


def _handle_cancellation(
    source: SourceEmail,
    event,
    state: SyncState,
    calendar,
    options: SyncOptions,
    summary: SyncSummary,
    planned_bookings: dict[str, object],
) -> None:
    existing = state.find_booking_for_cancellation(event)
    planned_event = _find_planned_cancellation_target(event, planned_bookings)
    if not existing:
        if options.dry_run and planned_event:
            print(f"DRY-RUN would cancel: {planned_event.title} at {_when(planned_event)}")
            summary.cancelled += 1
            return
        summary.skipped += 1
        print(f"SKIP cancellation with no matching booking: {event.title}")
        if not options.dry_run:
            state.record_message(source, event, "cancel-no-match")
        return

    fallback_event = row_to_event(existing)
    cancelled_event = fallback_event.__class__(
        **{**fallback_event.__dict__, "status": "cancelled", "source_message_id": source.message_id}
    )

    if options.dry_run:
        print(f"DRY-RUN would cancel: {fallback_event.title} at {_when(fallback_event)}")
        return

    result = calendar.cancel_event(
        existing["calendar_uid"],
        cancelled_event,
        existing_href=existing["calendar_href"],
    )
    state.mark_booking_cancelled(existing["fingerprint"], source.message_id)
    state.record_message(source, event, result.action)
    summary.cancelled += 1
    print(f"{result.action.upper()}: {fallback_event.title} at {_when(fallback_event)}")


def _when(event) -> str:
    if not event.start_at:
        return "unknown time"
    return event.start_at.strftime("%Y-%m-%d %H:%M")


def _event_in_date_scope(event, options: SyncOptions) -> bool:
    if not options.on_date and not options.from_date and not options.to_date:
        return True
    if event.start_at is None:
        return False
    event_date = event.start_at.date()
    if options.on_date and event_date != options.on_date:
        return False
    if options.from_date and event_date < options.from_date:
        return False
    if options.to_date and event_date > options.to_date:
        return False
    return True


def _format_reminder(minutes: int) -> str:
    if minutes % (24 * 60) == 0:
        days = minutes // (24 * 60)
        return f"{days} day" + ("" if days == 1 else "s")
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" + ("" if hours == 1 else "s")
    return f"{minutes} minutes"


def _apply_known_location(event, known_locations: dict[str, str]):
    if not event.studio:
        return event
    known = known_locations.get(event.studio.lower())
    if not known:
        return event
    if event.location and _is_rich_location(event.location):
        return event
    return replace(event, location=known)


def _is_rich_location(location: str) -> bool:
    return bool(
        re.search(r"\b\d{5}\b", location)
        or re.search(r"\b(DE|Germany|Deutschland)\b", location, flags=re.IGNORECASE)
    )


def _find_planned_cancellation_target(event, planned_bookings: dict[str, object]):
    if event.fingerprint in planned_bookings:
        return planned_bookings[event.fingerprint]
    if event.booking_id:
        for planned in planned_bookings.values():
            if getattr(planned, "booking_id", None) == event.booking_id:
                return planned
    for planned in planned_bookings.values():
        if (
            getattr(planned, "title", "").lower() == event.title.lower()
            and (getattr(planned, "studio", None) or "").lower() == (event.studio or "").lower()
        ):
            return planned
    return None
