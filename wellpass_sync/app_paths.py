from __future__ import annotations

import os
import platform
from pathlib import Path


APP_NAME = "Wellpass Calendar Sync"
APP_SLUG = "wellpass-calendar-sync"


def user_config_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        root = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / APP_NAME
    elif system == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        root = os.environ.get("XDG_CONFIG_HOME")
        if root:
            return Path(root) / APP_SLUG
        return Path.home() / ".config" / APP_SLUG
    return Path.home() / f".{APP_SLUG}"


def default_env_path() -> Path:
    return user_config_dir() / ".env"


def ensure_default_env_file(env_path: str | Path | None = None) -> Path:
    path = Path(env_path).expanduser() if env_path else default_env_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_default_env_text(), encoding="utf-8")
    return path


def _default_env_text() -> str:
    return "\n".join(
        [
            "# General",
            "TIMEZONE=Europe/Berlin",
            "",
            "# Email",
            "EMAIL_PROVIDER=graph",
            "EMAIL_SENDER_HINTS=Wellpass,noreply-de@egym-wellpass.com",
            "SEARCH_SINCE_DAYS=30",
            "IMAP_MAX_MESSAGES=100",
            "IMAP_PROVIDER=auto",
            "IMAP_HOST=",
            "IMAP_PORT=993",
            "IMAP_USERNAME=",
            "IMAP_PASSWORD=",
            "IMAP_FOLDER=INBOX",
            "",
            "# Microsoft Graph",
            "GRAPH_CLIENT_ID=",
            "GRAPH_TENANT=consumers",
            "GRAPH_SCOPES=Mail.Read",
            "GRAPH_TOKEN_CACHE=data/graph-token-cache.json",
            "",
            "# Google OAuth",
            "GOOGLE_CLIENT_SECRETS_PATH=google-oauth-client.json",
            "GOOGLE_TOKEN_CACHE=data/google-token-cache.json",
            "",
            "# Calendar",
            "CALENDAR_PROVIDER=icloud_caldav",
            "CALENDAR_NAME=Wellpass",
            "CALDAV_URL=https://caldav.icloud.com",
            "ICLOUD_USERNAME=",
            "ICLOUD_APP_PASSWORD=",
            "CALENDAR_REMINDER_MINUTES=",
            "",
            "# Local state",
            "DATABASE_PATH=data/wellpass-sync.sqlite",
            "ICS_EXPORT_DIR=exports",
            "",
            "# Scheduling",
            "TASK_NAME=Wellpass Calendar Sync",
            "TASK_INTERVAL_MINUTES=30",
            "",
        ]
    )
