from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .secrets import get_secret

MICROSOFT_GRAPH_COMMAND_LINE_TOOLS_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

CONFIG_VALUE_KEYS = (
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


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _get(values: dict[str, str], key: str, default: str = "") -> str:
    return os.environ.get(key, values.get(key, default))


def _get_secret_backed(values: dict[str, str], key: str, default: str = "") -> str:
    value = _get(values, key, "")
    if value:
        return value
    return get_secret(key) or default


def _bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _csv(value: str) -> list[str]:
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def _csv_preserve_case(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _csv_ints(value: str) -> list[int]:
    values: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            continue
    return values


def _config_path(value: str, default: Path, base_dir: Path) -> Path:
    if not value:
        return default
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    normalized = value.replace("\\", os.sep).replace("/", os.sep)
    return base_dir / Path(normalized)


@dataclass(frozen=True)
class AppConfig:
    env_path: Path
    timezone: str
    email_provider: str
    imap_provider: str
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    imap_folder: str
    graph_client_id: str
    graph_tenant: str
    graph_scopes: list[str]
    graph_token_cache: Path
    google_client_secrets_path: Path
    google_token_cache: Path
    email_sender_hints: list[str]
    email_subject_hints: list[str]
    email_body_hints: list[str]
    search_since_days: int
    imap_max_messages: int
    calendar_provider: str
    calendar_name: str
    caldav_url: str
    icloud_username: str
    icloud_app_password: str
    reminder_minutes: list[int]
    ics_export_dir: Path
    dry_run: bool
    database_path: Path
    task_name: str
    task_interval_minutes: int

    def validate_imap(self) -> None:
        missing = [
            name
            for name, value in {
                "IMAP_HOST": self.imap_host,
                "IMAP_USERNAME": self.imap_username,
                "IMAP_PASSWORD": self.imap_password,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing IMAP settings: {', '.join(missing)}")

    def validate_calendar_write(self) -> None:
        if self.calendar_provider in {"google_calendar", "outlook_calendar"}:
            return
        if self.calendar_provider in {"icloud_caldav", "caldav"}:
            missing = [
                name
                for name, value in {
                    "ICLOUD_USERNAME": self.icloud_username,
                    "ICLOUD_APP_PASSWORD": self.icloud_app_password,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"Missing iCloud CalDAV settings: {', '.join(missing)}")
        elif self.calendar_provider != "ics":
            raise ValueError(f"Unsupported CALENDAR_PROVIDER={self.calendar_provider!r}")

    def validate_graph(self) -> None:
        if not self.graph_client_id:
            raise ValueError(
                "Missing GRAPH_CLIENT_ID. Leave it unset to use the built-in default, "
                "or set GRAPH_CLIENT_ID to a Microsoft Entra public-client app ID."
            )


def load_config(env_path: str | Path = ".env") -> AppConfig:
    path = Path(env_path).expanduser()
    base_dir = path.resolve().parent
    values = _parse_env_file(path)
    return load_config_from_values(values, base_dir=base_dir, env_path=path)


def load_config_from_values(values: dict[str, str], base_dir: str | Path, env_path: str | Path | None = None) -> AppConfig:
    base_dir = Path(base_dir).expanduser().resolve()
    path = Path(env_path).expanduser() if env_path else base_dir / "Credential Manager"

    database_path = _config_path(
        _get(values, "DATABASE_PATH"),
        base_dir / "data" / "wellpass-sync.sqlite",
        base_dir,
    )
    ics_export_dir = _config_path(
        _get(values, "ICS_EXPORT_DIR"),
        base_dir / "exports",
        base_dir,
    )
    google_client_secrets_path = _config_path(
        _get(values, "GOOGLE_CLIENT_SECRETS_PATH"),
        base_dir / "google-oauth-client.json",
        base_dir,
    )
    google_token_cache = _config_path(
        _get(values, "GOOGLE_TOKEN_CACHE"),
        base_dir / "data" / "google-token-cache.json",
        base_dir,
    )

    email_provider = _get(values, "EMAIL_PROVIDER", "graph").lower()
    imap_provider = _get(values, "IMAP_PROVIDER", "auto").lower()
    imap_username = _get(values, "IMAP_USERNAME")
    imap_host = _get(values, "IMAP_HOST") or _default_imap_host(imap_provider, imap_username)

    return AppConfig(
        env_path=path,
        timezone=_get(values, "TIMEZONE", "Europe/Berlin"),
        email_provider=email_provider,
        imap_provider=imap_provider,
        imap_host=imap_host,
        imap_port=_int(_get(values, "IMAP_PORT", "993"), 993),
        imap_username=imap_username,
        imap_password=_get_secret_backed(values, "IMAP_PASSWORD"),
        imap_folder=_get(values, "IMAP_FOLDER", "INBOX"),
        graph_client_id=_get(values, "GRAPH_CLIENT_ID") or MICROSOFT_GRAPH_COMMAND_LINE_TOOLS_CLIENT_ID,
        graph_tenant=_get(values, "GRAPH_TENANT", "consumers"),
        graph_scopes=_csv_preserve_case(_get(values, "GRAPH_SCOPES", "Mail.Read")),
        graph_token_cache=_config_path(
            _get(values, "GRAPH_TOKEN_CACHE"),
            base_dir / "data" / "graph-token-cache.json",
            base_dir,
        ),
        google_client_secrets_path=google_client_secrets_path,
        google_token_cache=google_token_cache,
        email_sender_hints=_csv(_get(values, "EMAIL_SENDER_HINTS", "Wellpass,noreply-de@egym-wellpass.com")),
        email_subject_hints=_csv(
            _get(
                values,
                "EMAIL_SUBJECT_HINTS",
                "booking,reservation,buchung,storniert,cancelled,cancellation",
            )
        ),
        email_body_hints=_csv(_get(values, "EMAIL_BODY_HINTS", "wellpass,egym")),
        search_since_days=_int(_get(values, "SEARCH_SINCE_DAYS", "30"), 30),
        imap_max_messages=_int(_get(values, "IMAP_MAX_MESSAGES", "100"), 100),
        calendar_provider=_get(values, "CALENDAR_PROVIDER", "icloud_caldav").lower(),
        calendar_name=_get(values, "CALENDAR_NAME", "Wellpass"),
        caldav_url=_get(values, "CALDAV_URL", "https://caldav.icloud.com"),
        icloud_username=_get(values, "ICLOUD_USERNAME"),
        icloud_app_password=_get_secret_backed(values, "ICLOUD_APP_PASSWORD"),
        reminder_minutes=_csv_ints(_get(values, "CALENDAR_REMINDER_MINUTES", "")),
        ics_export_dir=ics_export_dir,
        dry_run=_bool(_get(values, "DRY_RUN", "true"), True),
        database_path=database_path,
        task_name=_get(values, "TASK_NAME", "Wellpass Calendar Sync"),
        task_interval_minutes=_int(_get(values, "TASK_INTERVAL_MINUTES", "30"), 30),
    )


def config_to_values(config: AppConfig, absolute_paths: bool = False) -> dict[str, str]:
    def path_value(path: Path) -> str:
        return str(path.resolve()) if absolute_paths else str(path)

    return {
        "TIMEZONE": config.timezone,
        "EMAIL_PROVIDER": config.email_provider,
        "EMAIL_SENDER_HINTS": ",".join(config.email_sender_hints),
        "SEARCH_SINCE_DAYS": str(config.search_since_days),
        "IMAP_MAX_MESSAGES": str(config.imap_max_messages),
        "IMAP_PROVIDER": config.imap_provider,
        "IMAP_HOST": config.imap_host,
        "IMAP_PORT": str(config.imap_port),
        "IMAP_USERNAME": config.imap_username,
        "IMAP_FOLDER": config.imap_folder,
        "GRAPH_CLIENT_ID": "" if config.graph_client_id == MICROSOFT_GRAPH_COMMAND_LINE_TOOLS_CLIENT_ID else config.graph_client_id,
        "GRAPH_TENANT": config.graph_tenant,
        "GRAPH_SCOPES": ",".join(config.graph_scopes),
        "GRAPH_TOKEN_CACHE": path_value(config.graph_token_cache),
        "GOOGLE_CLIENT_SECRETS_PATH": path_value(config.google_client_secrets_path),
        "GOOGLE_TOKEN_CACHE": path_value(config.google_token_cache),
        "CALENDAR_PROVIDER": config.calendar_provider,
        "CALENDAR_NAME": config.calendar_name,
        "CALDAV_URL": config.caldav_url,
        "ICLOUD_USERNAME": config.icloud_username,
        "CALENDAR_REMINDER_MINUTES": ",".join(str(value) for value in config.reminder_minutes),
        "DATABASE_PATH": path_value(config.database_path),
        "ICS_EXPORT_DIR": path_value(config.ics_export_dir),
        "TASK_NAME": config.task_name,
        "TASK_INTERVAL_MINUTES": str(config.task_interval_minutes),
    }


def _default_imap_host(imap_provider: str, username: str) -> str:
    if imap_provider and imap_provider != "auto":
        return _IMAP_HOST_PRESETS.get(imap_provider, "")
    domain = username.split("@", 1)[1].lower() if "@" in username else ""
    if domain in {"gmail.com", "googlemail.com"}:
        return _IMAP_HOST_PRESETS["gmail"]
    if domain in {"outlook.com", "hotmail.com", "live.com", "msn.com"}:
        return _IMAP_HOST_PRESETS["outlook"]
    if domain in {"icloud.com", "me.com", "mac.com"}:
        return _IMAP_HOST_PRESETS["icloud"]
    if domain in {"yahoo.com", "ymail.com", "rocketmail.com"}:
        return _IMAP_HOST_PRESETS["yahoo"]
    if domain.endswith("fastmail.com"):
        return _IMAP_HOST_PRESETS["fastmail"]
    return ""


_IMAP_HOST_PRESETS = {
    "gmail": "imap.gmail.com",
    "google": "imap.gmail.com",
    "outlook": "outlook.office365.com",
    "microsoft": "outlook.office365.com",
    "icloud": "imap.mail.me.com",
    "apple": "imap.mail.me.com",
    "yahoo": "imap.mail.yahoo.com",
    "fastmail": "imap.fastmail.com",
}
