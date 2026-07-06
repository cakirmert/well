from __future__ import annotations

import contextlib
import io
import queue
import re
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from .app_paths import ensure_default_env_file
from .calendar import calendar_exists, list_calendar_names
from .config import load_config
from .google_auth import GMAIL_READ_SCOPE, GOOGLE_CALENDAR_SCOPE, get_google_credentials
from .graph_mail import get_graph_access_token
from .scheduler import install_task, uninstall_task
from .secrets import set_secret
from .sync import SyncOptions, run_sync


EMAIL_PROVIDER_LABELS = {
    "Outlook / Microsoft 365": "graph",
    "Gmail": "gmail_oauth",
    "iCloud or other IMAP": "imap",
    "Classic desktop Outlook": "outlook",
}
CALENDAR_PROVIDER_LABELS = {
    "iCloud Calendar": "icloud_caldav",
    "Google Calendar": "google_calendar",
    "Outlook Calendar": "outlook_calendar",
    "ICS file only": "ics",
}


def run_gui(env_path: str | Path | None = None) -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
    except ImportError as exc:
        raise RuntimeError("The GUI requires tkinter. Install a Python distribution that includes Tcl/Tk.") from exc

    app = _GuiApp(tk, ttk, scrolledtext, filedialog, messagebox, ensure_default_env_file(env_path))
    app.run()
    return 0


def main() -> int:
    return run_gui()


class _GuiApp:
    def __init__(self, tk, ttk, scrolledtext, filedialog, messagebox, env_path: Path) -> None:
        self.tk = tk
        self.ttk = ttk
        self.scrolledtext = scrolledtext
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.env_path = env_path
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Wellpass Calendar Sync")
        self.root.geometry("880x680")
        self.root.minsize(780, 620)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.vars = {
            "TIMEZONE": tk.StringVar(value="Europe/Berlin"),
            "EMAIL_PROVIDER": tk.StringVar(value="graph"),
            "EMAIL_PROVIDER_LABEL": tk.StringVar(value="Outlook / Microsoft 365"),
            "EMAIL_SENDER_HINTS": tk.StringVar(value="Wellpass,noreply-de@egym-wellpass.com"),
            "SEARCH_SINCE_DAYS": tk.StringVar(value="30"),
            "IMAP_MAX_MESSAGES": tk.StringVar(value="100"),
            "IMAP_PROVIDER": tk.StringVar(value="auto"),
            "IMAP_HOST": tk.StringVar(value=""),
            "IMAP_PORT": tk.StringVar(value="993"),
            "IMAP_USERNAME": tk.StringVar(value=""),
            "IMAP_FOLDER": tk.StringVar(value="INBOX"),
            "GRAPH_CLIENT_ID": tk.StringVar(value=""),
            "GRAPH_TENANT": tk.StringVar(value="consumers"),
            "GRAPH_SCOPES": tk.StringVar(value="Mail.Read"),
            "GRAPH_TOKEN_CACHE": tk.StringVar(value="data/graph-token-cache.json"),
            "GOOGLE_CLIENT_SECRETS_PATH": tk.StringVar(value="google-oauth-client.json"),
            "GOOGLE_TOKEN_CACHE": tk.StringVar(value="data/google-token-cache.json"),
            "CALENDAR_PROVIDER": tk.StringVar(value="icloud_caldav"),
            "CALENDAR_PROVIDER_LABEL": tk.StringVar(value="iCloud Calendar"),
            "CALENDAR_NAME": tk.StringVar(value="Wellpass"),
            "CALDAV_URL": tk.StringVar(value="https://caldav.icloud.com"),
            "ICLOUD_USERNAME": tk.StringVar(value=""),
            "CALENDAR_REMINDER_MINUTES": tk.StringVar(value=""),
            "DATABASE_PATH": tk.StringVar(value="data/wellpass-sync.sqlite"),
            "ICS_EXPORT_DIR": tk.StringVar(value="exports"),
            "TASK_NAME": tk.StringVar(value="Wellpass Calendar Sync"),
            "TASK_INTERVAL_MINUTES": tk.StringVar(value="30"),
            "ICLOUD_SECRET": tk.StringVar(value=""),
            "IMAP_SECRET": tk.StringVar(value=""),
        }
        self.status_var = tk.StringVar(value="Ready")
        self.email_help_var = tk.StringVar()
        self.calendar_help_var = tk.StringVar()
        self.scheduler_stop = threading.Event()
        self.scheduler_thread: threading.Thread | None = None

        self._build()
        self._load_env_into_form()
        self._poll_log_queue()

    def run(self) -> None:
        self.root.mainloop()

    def _build(self) -> None:
        notebook = self.ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        setup = self.ttk.Frame(notebook, padding=14)
        run = self.ttk.Frame(notebook, padding=14)
        schedule = self.ttk.Frame(notebook, padding=14)
        advanced = self.ttk.Frame(notebook, padding=14)
        notebook.add(setup, text="Setup")
        notebook.add(run, text="Run")
        notebook.add(schedule, text="Automatic Sync")
        notebook.add(advanced, text="Advanced")

        self._build_setup(setup)
        self._build_run(run)
        self._build_schedule(schedule)
        self._build_advanced(advanced)

        status = self.ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status.pack(fill="x", padx=12, pady=(0, 8))

    def _build_setup(self, parent) -> None:
        parent.columnconfigure(0, weight=1)

        title = self.ttk.Label(parent, text="Connect your email and calendar", font=("", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")
        subtitle = self.ttk.Label(
            parent,
            text="Pick where your Wellpass emails arrive, then pick where calendar events should go.",
            anchor="w",
            wraplength=760,
        )
        subtitle.grid(row=1, column=0, sticky="ew", pady=(4, 14))

        email = self.ttk.LabelFrame(parent, text="1. Wellpass emails", padding=12)
        email.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        email.columnconfigure(1, weight=1)
        self.ttk.Label(email, text="Email account").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.email_provider_combo = self.ttk.Combobox(
            email,
            textvariable=self.vars["EMAIL_PROVIDER_LABEL"],
            values=tuple(EMAIL_PROVIDER_LABELS),
            state="readonly",
        )
        self.email_provider_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.email_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_provider_ui())
        self.email_signin_button = self.ttk.Button(email, text="Sign in", command=self._email_sign_in)
        self.email_signin_button.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=4)
        self.ttk.Label(email, textvariable=self.email_help_var, wraplength=720).grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(4, 0),
        )
        self.email_imap_frame = self.ttk.Frame(email)
        self.email_imap_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.email_imap_frame.columnconfigure(1, weight=1)
        self._field(self.email_imap_frame, 0, "Email address", "IMAP_USERNAME")
        self._secret_field(
            self.email_imap_frame,
            1,
            "Email password",
            "IMAP_SECRET",
            "Save password",
            lambda: self._store_secret("IMAP_PASSWORD", "IMAP_SECRET", "Email password saved securely."),
        )

        calendar = self.ttk.LabelFrame(parent, text="2. Calendar", padding=12)
        calendar.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        calendar.columnconfigure(1, weight=1)
        self.ttk.Label(calendar, text="Calendar account").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.calendar_provider_combo = self.ttk.Combobox(
            calendar,
            textvariable=self.vars["CALENDAR_PROVIDER_LABEL"],
            values=tuple(CALENDAR_PROVIDER_LABELS),
            state="readonly",
        )
        self.calendar_provider_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.calendar_provider_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_provider_ui())
        self.calendar_signin_button = self.ttk.Button(calendar, text="Sign in", command=self._calendar_sign_in)
        self.calendar_signin_button.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=4)
        self.ttk.Label(calendar, textvariable=self.calendar_help_var, wraplength=720).grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(4, 0),
        )
        self.icloud_calendar_frame = self.ttk.Frame(calendar)
        self.icloud_calendar_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.icloud_calendar_frame.columnconfigure(1, weight=1)
        self._field(self.icloud_calendar_frame, 0, "Apple Account email", "ICLOUD_USERNAME")
        self._secret_field(
            self.icloud_calendar_frame,
            1,
            "App-specific password",
            "ICLOUD_SECRET",
            "Save password",
            lambda: self._store_secret("ICLOUD_APP_PASSWORD", "ICLOUD_SECRET", "iCloud calendar password saved securely."),
        )

        calendar_choice = self.ttk.Frame(calendar)
        calendar_choice.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        calendar_choice.columnconfigure(1, weight=1)
        self.ttk.Label(calendar_choice, text="Use calendar").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.calendar_name_combo = self.ttk.Combobox(calendar_choice, textvariable=self.vars["CALENDAR_NAME"], values=())
        self.calendar_name_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.ttk.Button(calendar_choice, text="Find calendars", command=self._refresh_calendars).grid(
            row=0,
            column=2,
            padx=(8, 0),
            pady=4,
        )
        self.ttk.Button(calendar_choice, text="Use Wellpass", command=lambda: self.vars["CALENDAR_NAME"].set("Wellpass")).grid(
            row=0,
            column=3,
            padx=(8, 0),
            pady=4,
        )

        ready = self.ttk.LabelFrame(parent, text="3. Test and sync", padding=12)
        ready.grid(row=4, column=0, sticky="ew")
        self.ttk.Button(
            ready,
            text="Test run - no changes",
            command=lambda: self._save_then_run("Test run", self._run_once, True),
        ).pack(side="left", padx=(0, 8))
        self.ttk.Button(
            ready,
            text="Sync now",
            command=lambda: self._save_then_run("Sync now", self._run_once, False),
        ).pack(side="left", padx=(0, 8))
        self.ttk.Button(ready, text="Save setup", command=self._save_settings).pack(side="left")

    def _build_run(self, parent) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        top = self.ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.ttk.Button(
            top,
            text="Test run - no calendar changes",
            command=lambda: self._save_then_run("Test run", self._run_once, True),
        ).pack(side="left", padx=(0, 8))
        self.ttk.Button(
            top,
            text="Sync bookings now",
            command=lambda: self._save_then_run("Sync now", self._run_once, False),
        ).pack(side="left", padx=(0, 8))
        self.ttk.Button(top, text="Check calendar access", command=lambda: self._save_then_run("Check calendar", self._check_calendar)).pack(
            side="left",
            padx=(0, 8),
        )
        self.ttk.Button(top, text="Clear log", command=self._clear_log).pack(side="right")

        self.log_text = self.scrolledtext.ScrolledText(parent, wrap="word", height=20)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

    def _build_schedule(self, parent) -> None:
        parent.columnconfigure(0, weight=1)
        title = self.ttk.Label(parent, text="Automatic sync", font=("", 16, "bold"))
        title.grid(row=0, column=0, sticky="w")
        self.ttk.Label(
            parent,
            text="Turn this on after a successful test run. It uses your operating system scheduler, so it keeps working after the app is closed.",
            wraplength=760,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 16))

        frame = self.ttk.LabelFrame(parent, text="Schedule", padding=12)
        frame.grid(row=2, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)
        self._field(frame, 0, "Run every minutes", "TASK_INTERVAL_MINUTES")
        buttons = self.ttk.Frame(frame)
        buttons.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.ttk.Button(
            buttons,
            text="Turn on automatic sync",
            command=lambda: self._save_then_run("Turn on automatic sync", self._os_scheduler, False, True),
        ).pack(side="left", padx=(0, 8))
        self.ttk.Button(
            buttons,
            text="Turn off automatic sync",
            command=lambda: self._save_then_run("Turn off automatic sync", self._os_scheduler, False, False),
        ).pack(side="left")

        fallback = self.ttk.LabelFrame(parent, text="While this window is open", padding=12)
        fallback.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self.ttk.Button(fallback, text="Start temporary sync", command=self._start_in_app_scheduler).pack(side="left", padx=(0, 8))
        self.ttk.Button(fallback, text="Stop temporary sync", command=self._stop_in_app_scheduler).pack(side="left")

    def _build_advanced(self, parent) -> None:
        parent.columnconfigure(1, weight=1)
        row = 0
        self.ttk.Label(
            parent,
            text="Advanced settings. Most users do not need these.",
            font=("", 12, "bold"),
        ).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        row += 1
        row = self._field(parent, row, "Config file", None, button=("Browse", self._choose_env))
        self.env_label = self.ttk.Label(parent, text=str(self.env_path), anchor="w")
        self.env_label.grid(row=row - 1, column=1, sticky="ew", padx=6, pady=4)
        row = self._field(parent, row, "Timezone", "TIMEZONE")
        row = self._field(parent, row, "Search last days", "SEARCH_SINCE_DAYS")
        row = self._field(parent, row, "Maximum emails", "IMAP_MAX_MESSAGES")
        row = self._field(parent, row, "Wellpass sender hints", "EMAIL_SENDER_HINTS")
        row = self._combo(parent, row, "IMAP preset", "IMAP_PROVIDER", ("auto", "gmail", "outlook", "icloud", "yahoo", "fastmail", "custom"))
        row = self._field(parent, row, "IMAP host", "IMAP_HOST")
        row = self._field(parent, row, "IMAP port", "IMAP_PORT")
        row = self._field(parent, row, "IMAP folder", "IMAP_FOLDER")
        row = self._field(parent, row, "Microsoft app id", "GRAPH_CLIENT_ID")
        row = self._field(parent, row, "Microsoft tenant", "GRAPH_TENANT")
        row = self._field(parent, row, "Microsoft scopes", "GRAPH_SCOPES")
        row = self._field(parent, row, "Microsoft token file", "GRAPH_TOKEN_CACHE")
        row = self._file_field(parent, row, "Google OAuth JSON", "GOOGLE_CLIENT_SECRETS_PATH")
        row = self._field(parent, row, "Google token file", "GOOGLE_TOKEN_CACHE")
        row = self._field(parent, row, "CalDAV URL", "CALDAV_URL")
        row = self._field(parent, row, "Calendar reminders", "CALENDAR_REMINDER_MINUTES")
        row = self._field(parent, row, "SQLite file", "DATABASE_PATH")
        row = self._field(parent, row, "ICS export folder", "ICS_EXPORT_DIR")
        row = self._field(parent, row, "Scheduler task name", "TASK_NAME")
        row = self._button_row(
            parent,
            row,
            (
                ("Save advanced settings", self._save_settings),
                ("Open config folder", self._open_config_folder),
                ("Preview scheduler command", lambda: self._save_then_run("Preview scheduler", self._os_scheduler, True, True)),
            ),
        )

    def _field(self, parent, row: int, label: str, key: str | None, button=None) -> int:
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        if key:
            self.ttk.Entry(parent, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        if button:
            text, command = button
            self.ttk.Button(parent, text=text, command=command).grid(row=row, column=2, sticky="e", padx=(8, 0), pady=4)
        return row + 1

    def _secret_field(self, parent, row: int, label: str, key: str, button_text: str, command) -> int:
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        self.ttk.Entry(parent, textvariable=self.vars[key], show="*").grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        self.ttk.Button(parent, text=button_text, command=command).grid(row=row, column=2, sticky="e", padx=(8, 0), pady=4)
        return row + 1

    def _file_field(self, parent, row: int, label: str, key: str) -> int:
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        self.ttk.Entry(parent, textvariable=self.vars[key]).grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        self.ttk.Button(parent, text="Browse", command=lambda: self._choose_file(key)).grid(row=row, column=2, sticky="e", padx=(8, 0), pady=4)
        return row + 1

    def _combo(self, parent, row: int, label: str, key: str, values: tuple[str, ...]) -> int:
        self.ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        combo = self.ttk.Combobox(parent, textvariable=self.vars[key], values=values)
        combo.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        return row + 1

    def _button_row(self, parent, row: int, buttons: tuple[tuple[str, object], ...]) -> int:
        frame = self.ttk.Frame(parent)
        frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=6, pady=8)
        for text, command in buttons:
            self.ttk.Button(frame, text=text, command=command).pack(side="left", padx=(0, 8))
        return row + 1

    def _choose_env(self) -> None:
        selected = self.filedialog.askopenfilename(
            title="Choose app settings file",
            filetypes=(("Environment files", "*.env"), ("All files", "*.*")),
        )
        if selected:
            self.env_path = Path(selected)
            self.env_label.configure(text=str(self.env_path))
            self._load_env_into_form()

    def _choose_file(self, key: str) -> None:
        selected = self.filedialog.askopenfilename(
            title="Choose file",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if selected:
            self.vars[key].set(selected)

    def _load_env_into_form(self) -> None:
        config = load_config(self.env_path)
        values = {
            "TIMEZONE": config.timezone,
            "EMAIL_PROVIDER": config.email_provider,
            "EMAIL_PROVIDER_LABEL": _label_for_value(EMAIL_PROVIDER_LABELS, config.email_provider),
            "EMAIL_SENDER_HINTS": ",".join(config.email_sender_hints),
            "SEARCH_SINCE_DAYS": str(config.search_since_days),
            "IMAP_MAX_MESSAGES": str(config.imap_max_messages),
            "IMAP_PROVIDER": config.imap_provider,
            "IMAP_HOST": config.imap_host,
            "IMAP_PORT": str(config.imap_port),
            "IMAP_USERNAME": config.imap_username,
            "IMAP_FOLDER": config.imap_folder,
            "GRAPH_CLIENT_ID": "" if config.graph_client_id == "14d82eec-204b-4c2f-b7e8-296a70dab67e" else config.graph_client_id,
            "GRAPH_TENANT": config.graph_tenant,
            "GRAPH_SCOPES": ",".join(config.graph_scopes),
            "GRAPH_TOKEN_CACHE": _display_path(config.graph_token_cache, self.env_path),
            "GOOGLE_CLIENT_SECRETS_PATH": _display_path(config.google_client_secrets_path, self.env_path),
            "GOOGLE_TOKEN_CACHE": _display_path(config.google_token_cache, self.env_path),
            "CALENDAR_PROVIDER": config.calendar_provider,
            "CALENDAR_PROVIDER_LABEL": _label_for_value(CALENDAR_PROVIDER_LABELS, config.calendar_provider),
            "CALENDAR_NAME": config.calendar_name,
            "CALDAV_URL": config.caldav_url,
            "ICLOUD_USERNAME": config.icloud_username,
            "CALENDAR_REMINDER_MINUTES": ",".join(str(value) for value in config.reminder_minutes),
            "DATABASE_PATH": _display_path(config.database_path, self.env_path),
            "ICS_EXPORT_DIR": _display_path(config.ics_export_dir, self.env_path),
            "TASK_NAME": config.task_name,
            "TASK_INTERVAL_MINUTES": str(config.task_interval_minutes),
        }
        for key, value in values.items():
            self.vars[key].set(value)
        self._refresh_provider_ui()

    def _save_settings(self, log: bool = True) -> None:
        self._sync_provider_labels_to_values()
        updates = {key: self.vars[key].get().strip() for key in _ENV_KEYS if key in self.vars}
        updates["ICLOUD_APP_PASSWORD"] = ""
        updates["IMAP_PASSWORD"] = ""
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text(_render_env(updates), encoding="utf-8")
        if log:
            self._log("Setup saved.")
        self.status_var.set("Ready")

    def _sync_provider_labels_to_values(self) -> None:
        self.vars["EMAIL_PROVIDER"].set(
            EMAIL_PROVIDER_LABELS.get(self.vars["EMAIL_PROVIDER_LABEL"].get(), self.vars["EMAIL_PROVIDER"].get())
        )
        self.vars["CALENDAR_PROVIDER"].set(
            CALENDAR_PROVIDER_LABELS.get(self.vars["CALENDAR_PROVIDER_LABEL"].get(), self.vars["CALENDAR_PROVIDER"].get())
        )

    def _refresh_provider_ui(self) -> None:
        self._sync_provider_labels_to_values()
        email_provider = self.vars["EMAIL_PROVIDER"].get()
        calendar_provider = self.vars["CALENDAR_PROVIDER"].get()

        if email_provider == "graph":
            self.email_help_var.set("Use this when your Wellpass emails are in Outlook.com or Microsoft 365.")
            self.email_signin_button.configure(text="Sign in with Microsoft", state="normal")
            self.email_imap_frame.grid_remove()
        elif email_provider == "gmail_oauth":
            self.email_help_var.set("Use this when your Wellpass emails are in Gmail.")
            self.email_signin_button.configure(text="Sign in with Google", state="normal")
            self.email_imap_frame.grid_remove()
        elif email_provider == "imap":
            self.email_help_var.set("Use this for iCloud Mail or another mailbox. Enter the email address and app password.")
            self.email_signin_button.configure(text="Password saved below", state="disabled")
            self.email_imap_frame.grid()
        else:
            self.email_help_var.set("Uses the classic desktop Outlook profile on this computer.")
            self.email_signin_button.configure(text="No sign-in needed", state="disabled")
            self.email_imap_frame.grid_remove()

        if calendar_provider == "icloud_caldav":
            self.calendar_help_var.set("Use your Apple Account email and an app-specific password.")
            self.calendar_signin_button.configure(text="Password saved below", state="disabled")
            self.icloud_calendar_frame.grid()
        elif calendar_provider == "google_calendar":
            self.calendar_help_var.set("Use this when events should go to Google Calendar.")
            self.calendar_signin_button.configure(text="Sign in with Google", state="normal")
            self.icloud_calendar_frame.grid_remove()
        elif calendar_provider == "outlook_calendar":
            self.calendar_help_var.set("Use this when events should go to Outlook Calendar.")
            self.calendar_signin_button.configure(text="Sign in with Microsoft", state="normal")
            self.icloud_calendar_frame.grid_remove()
        else:
            self.calendar_help_var.set("Writes local .ics files only. This is useful for testing, but it does not update a cloud calendar.")
            self.calendar_signin_button.configure(text="No sign-in needed", state="disabled")
            self.icloud_calendar_frame.grid_remove()

    def _store_secret(self, secret_key: str, var_key: str, success_message: str) -> None:
        value = self.vars[var_key].get()
        if not value:
            self.messagebox.showerror("Missing password", "Enter the password first.")
            return
        try:
            set_secret(secret_key, value)
        except Exception as exc:
            self.messagebox.showerror("Could not save password", str(exc))
            return
        self.vars[var_key].set("")
        self._log(success_message)

    def _email_sign_in(self) -> None:
        self._sync_provider_labels_to_values()
        provider = self.vars["EMAIL_PROVIDER"].get()
        if provider == "graph":
            self._auth_graph({"Mail.Read"})
        elif provider == "gmail_oauth":
            self._auth_google({GMAIL_READ_SCOPE})

    def _calendar_sign_in(self) -> None:
        self._sync_provider_labels_to_values()
        provider = self.vars["CALENDAR_PROVIDER"].get()
        if provider == "outlook_calendar":
            self._auth_graph({"Calendars.ReadWrite"})
        elif provider == "google_calendar":
            self._auth_google({GOOGLE_CALENDAR_SCOPE})

    def _auth_graph(self, extra_scopes: set[str] | None = None) -> None:
        self._save_settings(log=False)
        self._run_worker("Microsoft sign-in", self._auth_graph_worker, extra_scopes or set())

    def _auth_google(self, extra_scopes: set[str] | None = None) -> None:
        self._save_settings(log=False)
        self._run_worker("Google sign-in", self._auth_google_worker, extra_scopes or set())

    def _auth_graph_worker(self, extra_scopes: set[str]) -> None:
        config = load_config(self.env_path)

        def prompt(flow: dict) -> None:
            url = flow.get("verification_uri") or "https://www.microsoft.com/link"
            code = flow.get("user_code", "")
            self._log(f"Microsoft sign-in opened. Enter this code if asked: {code}")
            webbrowser.open(url)
            self.root.after(
                0,
                lambda: self.messagebox.showinfo(
                    "Microsoft sign-in",
                    f"Your browser was opened.\n\nCode: {code}",
                ),
            )

        scopes = sorted(set(config.graph_scopes) | set(extra_scopes))
        get_graph_access_token(config, prompt_callback=prompt, scopes=scopes)
        self._log("Microsoft account connected.")

    def _auth_google_worker(self, extra_scopes: set[str]) -> None:
        config = load_config(self.env_path)
        scopes = set(extra_scopes)
        if config.email_provider == "gmail_oauth":
            scopes.add(GMAIL_READ_SCOPE)
        if config.calendar_provider == "google_calendar":
            scopes.add(GOOGLE_CALENDAR_SCOPE)
        if not scopes:
            scopes = {GMAIL_READ_SCOPE, GOOGLE_CALENDAR_SCOPE}
        self._log("Opening Google sign-in in your browser.")
        get_google_credentials(config, sorted(scopes))
        self._log("Google account connected.")

    def _refresh_calendars(self) -> None:
        self._save_settings(log=False)
        self._run_worker("Find calendars", self._refresh_calendars_worker)

    def _refresh_calendars_worker(self) -> None:
        config = load_config(self.env_path)
        names = list_calendar_names(config)
        self.root.after(0, lambda: self.calendar_name_combo.configure(values=names))
        if names:
            self._log(f"Found {len(names)} calendar(s). Choose one from the list, or type a new name.")
        else:
            self._log("No cloud calendars were listed. You can still type a new calendar name.")

    def _check_calendar(self) -> None:
        config = load_config(self.env_path)
        exists = calendar_exists(config, config.calendar_name)
        if exists:
            self._log(f"Calendar access works: {config.calendar_name}")
        else:
            self._log(f"Calendar was not found yet: {config.calendar_name}. It will be created during sync if the provider supports it.")

    def _run_once(self, dry_run: bool) -> None:
        config = load_config(self.env_path)
        options = SyncOptions(dry_run=dry_run, source="auto")
        run_sync(config, options)

    def _start_in_app_scheduler(self) -> None:
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self._log("Temporary sync is already running.")
            return
        self._save_settings(log=False)
        self.scheduler_stop.clear()
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        self._log("Temporary sync started. It stops when this window is closed.")
        self.status_var.set("Temporary sync running")

    def _stop_in_app_scheduler(self) -> None:
        self.scheduler_stop.set()
        self._log("Temporary sync stopped.")
        self.status_var.set("Ready")

    def _scheduler_loop(self) -> None:
        while not self.scheduler_stop.is_set():
            try:
                config = load_config(self.env_path)
                run_sync(config, SyncOptions(dry_run=False, source="auto"))
                interval_seconds = max(1, config.task_interval_minutes) * 60
            except Exception as exc:
                self._log(f"Automatic sync problem: {exc}")
                interval_seconds = 60
            self.scheduler_stop.wait(interval_seconds)

    def _os_scheduler(self, print_only: bool, install: bool) -> None:
        config = load_config(self.env_path)
        if install:
            install_task(
                task_name=config.task_name,
                interval_minutes=config.task_interval_minutes,
                env_path=self.env_path.resolve(),
                write=True,
                print_only=print_only,
            )
        else:
            uninstall_task(config.task_name, print_only=print_only)

    def _open_config_folder(self) -> None:
        webbrowser.open(self.env_path.resolve().parent.as_uri())

    def _save_then_run(self, label: str, func, *args) -> None:
        self._save_settings(log=False)
        self._run_worker(label, func, *args)

    def _run_worker(self, label: str, func, *args) -> None:
        def worker() -> None:
            self._set_status(f"{label} running")
            self._log(f"{label} started.")
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                    func(*args)
                self._log_command_output(buffer.getvalue())
                self._log(f"{label} finished.")
                self._set_status("Ready")
            except Exception as exc:
                self._log_command_output(buffer.getvalue())
                self._log(f"{label} failed: {exc}")
                self._set_status(f"{label} failed")
                self.root.after(0, lambda: self.messagebox.showerror(label, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, value: str) -> None:
        self.root.after(0, lambda: self.status_var.set(value))

    def _log(self, value: str) -> None:
        self.log_queue.put(value)

    def _log_command_output(self, output: str) -> None:
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            friendly = _friendly_log_line(line)
            if friendly:
                self._log(friendly)

    def _poll_log_queue(self) -> None:
        try:
            while True:
                value = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", f"[{_timestamp()}] {value}\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_close(self) -> None:
        self.scheduler_stop.set()
        self.root.destroy()


_ENV_KEYS = (
    "TIMEZONE",
    "EMAIL_PROVIDER",
    "EMAIL_SENDER_HINTS",
    "SEARCH_SINCE_DAYS",
    "IMAP_MAX_MESSAGES",
    "IMAP_PROVIDER",
    "IMAP_HOST",
    "IMAP_PORT",
    "IMAP_USERNAME",
    "IMAP_FOLDER",
    "GRAPH_CLIENT_ID",
    "GRAPH_TENANT",
    "GRAPH_SCOPES",
    "GRAPH_TOKEN_CACHE",
    "GOOGLE_CLIENT_SECRETS_PATH",
    "GOOGLE_TOKEN_CACHE",
    "CALENDAR_PROVIDER",
    "CALENDAR_NAME",
    "CALDAV_URL",
    "ICLOUD_USERNAME",
    "CALENDAR_REMINDER_MINUTES",
    "DATABASE_PATH",
    "ICS_EXPORT_DIR",
    "TASK_NAME",
    "TASK_INTERVAL_MINUTES",
)


def _render_env(values: dict[str, str]) -> str:
    sections = [
        ("General", ["TIMEZONE"]),
        (
            "Email",
            [
                "EMAIL_PROVIDER",
                "EMAIL_SENDER_HINTS",
                "SEARCH_SINCE_DAYS",
                "IMAP_MAX_MESSAGES",
                "IMAP_PROVIDER",
                "IMAP_HOST",
                "IMAP_PORT",
                "IMAP_USERNAME",
                "IMAP_PASSWORD",
                "IMAP_FOLDER",
            ],
        ),
        ("Microsoft Graph", ["GRAPH_CLIENT_ID", "GRAPH_TENANT", "GRAPH_SCOPES", "GRAPH_TOKEN_CACHE"]),
        ("Google OAuth", ["GOOGLE_CLIENT_SECRETS_PATH", "GOOGLE_TOKEN_CACHE"]),
        (
            "Calendar",
            [
                "CALENDAR_PROVIDER",
                "CALENDAR_NAME",
                "CALDAV_URL",
                "ICLOUD_USERNAME",
                "ICLOUD_APP_PASSWORD",
                "CALENDAR_REMINDER_MINUTES",
            ],
        ),
        ("Local state", ["DATABASE_PATH", "ICS_EXPORT_DIR"]),
        ("Scheduling", ["TASK_NAME", "TASK_INTERVAL_MINUTES"]),
    ]
    lines: list[str] = []
    for title, keys in sections:
        if lines:
            lines.append("")
        lines.append(f"# {title}")
        for key in keys:
            lines.append(f"{key}={values.get(key, '')}")
    lines.append("")
    return "\n".join(lines)


def _friendly_log_line(line: str) -> str:
    match = re.match(r"Loaded (\d+) candidate email\(s\) from (.+)\.", line)
    if match:
        return f"Checked {match.group(1)} recent email(s)."
    if line.startswith("Dry run:"):
        return "Test run only. Your calendar was not changed."
    if line.startswith("Calendar reminders:"):
        return line.replace("Calendar reminders:", "Event alerts:")
    if line.startswith("DRY-RUN would create:"):
        return "Would add: " + line.split(":", 1)[1].strip()
    if line.startswith("DRY-RUN would update:"):
        return "Would update: " + line.split(":", 1)[1].strip()
    if line.startswith("DRY-RUN would cancel:"):
        return "Would remove: " + line.split(":", 1)[1].strip()
    if line.startswith("CREATED:"):
        return "Added: " + line.split(":", 1)[1].strip()
    if line.startswith("UPDATED:"):
        return "Updated: " + line.split(":", 1)[1].strip()
    if line.startswith("DELETED:") or line.startswith("DELETED-EXPORT:"):
        return "Removed: " + line.split(":", 1)[1].strip()
    if line.startswith("MISSING:"):
        return "Already removed: " + line.split(":", 1)[1].strip()
    if line.startswith("SKIP unchanged:"):
        return "Already up to date: " + line.split(":", 1)[1].strip()
    if line.startswith("SKIP already processed:"):
        return "Already checked: " + line.split(":", 1)[1].strip()
    if line.startswith("SKIP cancellation with no matching booking:"):
        return "Cancellation email found, but no matching calendar event: " + line.split(":", 1)[1].strip()
    if line.startswith("IGNORE could not parse booking fields:"):
        return "Skipped an email I could not understand: " + line.split(":", 1)[1].strip()
    if line.startswith("ERROR "):
        return "Problem: " + line.removeprefix("ERROR ").strip()
    if line.startswith("Summary:"):
        return _friendly_summary(line)
    if line.startswith("Task action:") or line.startswith("schtasks command:"):
        return None
    if line.startswith("Print-only mode:"):
        return "Preview only. Automatic sync was not changed."
    if line.startswith("Installed scheduled task:"):
        return "Automatic sync is on."
    if line.startswith("Removed scheduled task:"):
        return "Automatic sync is off."
    return line


def _friendly_summary(line: str) -> str:
    values = dict(re.findall(r"(\w+)=(\d+)", line))
    if not values:
        return line
    parts = [
        f"checked {values.get('scanned', '0')}",
        f"understood {values.get('parsed', '0')}",
        f"added {values.get('created', '0')}",
        f"updated {values.get('updated', '0')}",
        f"removed {values.get('cancelled', '0')}",
        f"skipped {values.get('skipped', '0')}",
    ]
    errors = values.get("errors", "0")
    if errors != "0":
        parts.append(f"problems {errors}")
    return "Done: " + ", ".join(parts) + "."


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _display_path(path: Path, env_path: Path) -> str:
    try:
        return str(path.resolve().relative_to(env_path.resolve().parent))
    except ValueError:
        return str(path)


def _label_for_value(labels: dict[str, str], value: str) -> str:
    for label, candidate in labels.items():
        if candidate == value:
            return label
    return next(iter(labels))
