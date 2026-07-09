from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from .calendar import calendar_exists, list_calendar_names
from .config import load_config
from .email_source import load_sample_emails
from .graph_mail import get_graph_access_token
from .parser import parse_booking_email
from .scheduler import install_task, uninstall_task
from .secrets import SECRET_KEYS, delete_secret, set_secret
from .settings_store import import_env_to_store, load_stored_config
from .sync import SyncOptions, run_sync


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(prog="wellpass-sync")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run-once", help="Process matching emails once and sync calendar")
    _add_common_sync_args(run_parser)

    sync_parser = subparsers.add_parser("sync", help="Alias for run-once")
    _add_common_sync_args(sync_parser)

    parse_parser = subparsers.add_parser("parse-samples", help="Parse .eml files without writing state")
    parse_parser.add_argument("--env", default=".env")
    parse_parser.add_argument("--eml-dir", default="samples")

    check_calendar_parser = subparsers.add_parser(
        "check-calendar", help="Check whether an iCloud CalDAV calendar exists without writing"
    )
    check_calendar_parser.add_argument("--env", default=".env")
    check_calendar_parser.add_argument("--stored-settings", action="store_true", help="Use settings saved in the OS keychain")
    check_calendar_parser.add_argument("--calendar-name", required=True)

    list_calendars_parser = subparsers.add_parser("list-calendars", help="List calendars for the configured target")
    list_calendars_parser.add_argument("--env", default=".env")
    list_calendars_parser.add_argument("--stored-settings", action="store_true", help="Use settings saved in the OS keychain")

    gui_parser = subparsers.add_parser("gui", help="Open the desktop GUI")
    gui_parser.add_argument("--env", default=None)

    auth_graph_parser = subparsers.add_parser(
        "auth-graph", help="Sign in to Microsoft Graph and cache a local token"
    )
    auth_graph_parser.add_argument("--env", default=".env")
    auth_graph_parser.add_argument("--stored-settings", action="store_true", help="Use settings saved in the OS keychain")

    auth_google_parser = subparsers.add_parser(
        "auth-google", help="Sign in to Google and cache a local OAuth token"
    )
    auth_google_parser.add_argument("--env", default=".env")
    auth_google_parser.add_argument("--stored-settings", action="store_true", help="Use settings saved in the OS keychain")
    auth_google_parser.add_argument(
        "--scope",
        action="append",
        choices=["gmail", "calendar"],
        help="OAuth scope group to request. Defaults to gmail and calendar.",
    )

    set_secret_parser = subparsers.add_parser(
        "set-secret", help="Store a supported secret in the OS keychain"
    )
    set_secret_parser.add_argument("key", choices=sorted(SECRET_KEYS))

    delete_secret_parser = subparsers.add_parser(
        "delete-secret", help="Remove a supported secret from the OS keychain"
    )
    delete_secret_parser.add_argument("key", choices=sorted(SECRET_KEYS))

    install_parser = subparsers.add_parser("install-task", help="Install an OS scheduler job")
    install_parser.add_argument("--env", default=".env")
    install_parser.add_argument("--stored-settings", action="store_true", help="Use settings saved in the OS keychain")
    install_parser.add_argument("--task-name")
    install_parser.add_argument("--interval-minutes", type=int)
    install_parser.add_argument("--write", action="store_true", help="Scheduled job writes to calendar")
    install_parser.add_argument("--print-only", action="store_true", help="Print schtasks command without installing")

    uninstall_parser = subparsers.add_parser("uninstall-task", help="Remove the OS scheduler job")
    uninstall_parser.add_argument("--env", default=".env")
    uninstall_parser.add_argument("--stored-settings", action="store_true", help="Use settings saved in the OS keychain")
    uninstall_parser.add_argument("--task-name")
    uninstall_parser.add_argument("--print-only", action="store_true")

    import_env_parser = subparsers.add_parser("import-env", help="Import a .env setup into the OS keychain settings store")
    import_env_parser.add_argument("--env", default=".env")

    args = parser.parse_args(argv)

    if args.command in {"run-once", "sync"}:
        config = _load_selected_config(args)
        if args.calendar_name:
            config = replace(config, calendar_name=args.calendar_name)
        dry_run = config.dry_run
        if args.dry_run:
            dry_run = True
        if args.write:
            dry_run = False
        options = SyncOptions(
            source=args.source,
            sample_dir=Path(args.eml_dir),
            dry_run=dry_run,
            reprocess=args.reprocess,
            limit=args.limit,
            force_ics=args.ics_only,
            on_date=date.fromisoformat(args.on_date) if args.on_date else None,
            from_date=date.fromisoformat(args.from_date) if args.from_date else None,
            to_date=date.fromisoformat(args.to_date) if args.to_date else None,
            sender_contains=args.sender,
        )
        try:
            run_sync(config, options)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "parse-samples":
        config = load_config(args.env)
        messages = load_sample_emails(args.eml_dir)
        if not messages:
            print(f"No .eml files found in {args.eml_dir}.")
            return 0
        for source in messages:
            event = parse_booking_email(source, config.timezone)
            print(f"\n{source.subject}")
            if event is None:
                print("  could not parse")
                continue
            print(f"  status: {event.status}")
            print(f"  title: {event.title}")
            print(f"  studio: {event.studio or ''}")
            print(f"  start: {event.start_at or ''}")
            print(f"  end: {event.end_at or ''}")
            print(f"  location: {event.location or ''}")
            print(f"  booking_id: {event.booking_id or ''}")
            print(f"  fingerprint: {event.fingerprint}")
        return 0

    if args.command == "check-calendar":
        config = _load_selected_config(args)
        try:
            exists = calendar_exists(config, args.calendar_name)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        if exists:
            print(f"FOUND calendar: {args.calendar_name}")
            return 0
        print(f"DID NOT FIND calendar: {args.calendar_name}")
        return 1

    if args.command == "list-calendars":
        config = _load_selected_config(args)
        try:
            names = list_calendar_names(config)
        except (RuntimeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        for name in names:
            print(name)
        return 0

    if args.command == "gui":
        from .gui import run_gui

        try:
            return run_gui(args.env)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if args.command == "auth-graph":
        config = _load_selected_config(args)
        try:
            get_graph_access_token(config)
        except (RuntimeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print("Microsoft Graph sign-in is ready.")
        return 0

    if args.command == "auth-google":
        from .google_auth import GMAIL_READ_SCOPE, GOOGLE_CALENDAR_SCOPE, get_google_credentials

        config = _load_selected_config(args)
        scope_groups = set(args.scope or ["gmail", "calendar"])
        scopes = []
        if "gmail" in scope_groups:
            scopes.append(GMAIL_READ_SCOPE)
        if "calendar" in scope_groups:
            scopes.append(GOOGLE_CALENDAR_SCOPE)
        try:
            get_google_credentials(config, scopes)
        except (RuntimeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print("Google sign-in is ready.")
        return 0

    if args.command == "set-secret":
        try:
            set_secret(args.key)
        except (RuntimeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Stored {args.key} in the OS keychain.")
        return 0

    if args.command == "delete-secret":
        removed = delete_secret(args.key)
        if removed:
            print(f"Removed {args.key} from the OS keychain.")
            return 0
        print(f"No OS keychain entry found for {args.key}.")
        return 1

    if args.command == "install-task":
        config = _load_selected_config(args)
        install_task(
            task_name=args.task_name or config.task_name,
            interval_minutes=args.interval_minutes or config.task_interval_minutes,
            env_path=None if args.stored_settings else Path(args.env).resolve(),
            write=args.write,
            print_only=args.print_only,
            stored_settings=args.stored_settings,
        )
        return 0

    if args.command == "uninstall-task":
        config = _load_selected_config(args)
        uninstall_task(
            task_name=args.task_name or config.task_name,
            print_only=args.print_only,
        )
        return 0

    if args.command == "import-env":
        import_env_to_store(args.env)
        print("Imported settings into the OS keychain.")
        return 0

    parser.error(f"Unknown command {args.command}")
    return 2


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _load_selected_config(args) -> object:
    if getattr(args, "stored_settings", False):
        return load_stored_config()
    return load_config(args.env)


def _add_common_sync_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", default=".env")
    parser.add_argument("--stored-settings", action="store_true", help="Use settings saved in the OS keychain")
    parser.add_argument("--source", choices=["auto", "graph", "gmail_oauth", "imap", "outlook", "samples"], default="auto")
    parser.add_argument("--eml-dir", default="samples")
    parser.add_argument("--dry-run", action="store_true", help="Force dry run")
    parser.add_argument("--write", action="store_true", help="Write SQLite state and calendar changes")
    parser.add_argument("--reprocess", action="store_true", help="Reprocess messages already seen")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ics-only", action="store_true", help="Write .ics files instead of CalDAV")
    parser.add_argument("--on-date", help="Only process parsed events on this date, YYYY-MM-DD")
    parser.add_argument("--from-date", help="Only process parsed events on/after this date, YYYY-MM-DD")
    parser.add_argument("--to-date", help="Only process parsed events on/before this date, YYYY-MM-DD")
    parser.add_argument("--sender", help="Only process messages whose From header contains this text")
    parser.add_argument("--calendar-name", help="Override CALENDAR_NAME for this run")


if __name__ == "__main__":
    raise SystemExit(main())
