from __future__ import annotations

from pathlib import Path

from .config import AppConfig

GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"


def get_google_credentials(config: AppConfig, scopes: list[str]):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "Google OAuth support requires google-auth-oauthlib and google-api-python-client. "
            "Install dependencies with: python -m pip install -e ."
        ) from exc

    token_path = config.google_token_cache
    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), scopes=scopes)

    if credentials and credentials.valid and _has_scopes(credentials, scopes):
        return credentials

    if credentials and credentials.expired and credentials.refresh_token and _has_scopes(credentials, scopes):
        credentials.refresh(Request())
        _save_credentials(credentials, token_path)
        return credentials

    client_secrets = config.google_client_secrets_path
    if not client_secrets.exists():
        raise RuntimeError(
            "Google OAuth needs a Desktop OAuth client secrets JSON file. "
            "Set GOOGLE_CLIENT_SECRETS_PATH in Settings."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), scopes=scopes)
    credentials = flow.run_local_server(port=0)
    _save_credentials(credentials, token_path)
    return credentials


def build_google_service(config: AppConfig, api: str, version: str, scopes: list[str]):
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google API support requires google-api-python-client. "
            "Install dependencies with: python -m pip install -e ."
        ) from exc
    return build(api, version, credentials=get_google_credentials(config, scopes), cache_discovery=False)


def _save_credentials(credentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")


def _has_scopes(credentials, scopes: list[str]) -> bool:
    granted = set(credentials.scopes or [])
    return set(scopes).issubset(granted)
