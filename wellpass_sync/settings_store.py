from __future__ import annotations

import json
from pathlib import Path

from .app_paths import user_config_dir
from .config import CONFIG_VALUE_KEYS, AppConfig, config_to_values, load_config, load_config_from_values
from .secrets import SERVICE_NAME


SETTINGS_KEY = "APP_SETTINGS_JSON"


def settings_base_dir() -> Path:
    path = user_config_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_stored_settings() -> dict[str, str]:
    raw = _get_password(SETTINGS_KEY)
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: str(payload.get(key, "")) for key in CONFIG_VALUE_KEYS if key in payload}


def save_stored_settings(values: dict[str, str]) -> None:
    clean = {key: str(values.get(key, "")).strip() for key in CONFIG_VALUE_KEYS}
    _set_password(SETTINGS_KEY, json.dumps(clean, sort_keys=True))


def stored_settings_exist() -> bool:
    return bool(load_stored_settings())


def load_stored_config() -> AppConfig:
    return load_config_from_values(
        load_stored_settings(),
        base_dir=settings_base_dir(),
        env_path=settings_base_dir() / "Credential Manager",
    )


def save_config_to_store(config: AppConfig) -> None:
    save_stored_settings(config_to_values(config, absolute_paths=True))


def import_env_to_store(env_path: str | Path) -> AppConfig:
    config = load_config(env_path)
    save_config_to_store(config)
    return load_stored_config()


def _get_password(key: str) -> str:
    try:
        import keyring
    except ImportError:
        return ""
    try:
        return keyring.get_password(SERVICE_NAME, key) or ""
    except Exception:
        return ""


def _set_password(key: str, value: str) -> None:
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError(
            "Credential Manager storage requires keyring. Install dependencies with: python -m pip install -e ."
        ) from exc
    keyring.set_password(SERVICE_NAME, key, value)
