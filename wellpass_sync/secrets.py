from __future__ import annotations

import getpass


SERVICE_NAME = "wellpass-calendar-sync"

SECRET_KEYS = {
    "ICLOUD_APP_PASSWORD": "wellpass-sync/icloud-app-password",
    "IMAP_PASSWORD": "wellpass-sync/imap-password",
}


def get_secret(key: str) -> str:
    _target_for_key(key)
    value = _get_keyring_secret(key)
    if value:
        return value
    return _get_legacy_windows_secret(key)


def set_secret(key: str, value: str | None = None) -> None:
    _target_for_key(key)
    if value is None:
        value = getpass.getpass(f"{key}: ")
    if not value:
        raise ValueError(f"No value provided for {key}")

    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError(
            "Cross-platform secret storage requires keyring. "
            "Install dependencies with: python -m pip install -e ."
        ) from exc

    keyring.set_password(SERVICE_NAME, key, value)


def delete_secret(key: str) -> bool:
    _target_for_key(key)
    removed = _delete_keyring_secret(key)
    return _delete_legacy_windows_secret(key) or removed


def _get_keyring_secret(key: str) -> str:
    try:
        import keyring
    except ImportError:
        return ""

    try:
        return keyring.get_password(SERVICE_NAME, key) or ""
    except Exception:
        return ""


def _delete_keyring_secret(key: str) -> bool:
    try:
        import keyring
    except ImportError:
        return False

    try:
        keyring.delete_password(SERVICE_NAME, key)
        return True
    except Exception:
        return False


def _get_legacy_windows_secret(key: str) -> str:
    target = _target_for_key(key)
    try:
        import win32cred
    except ImportError:
        return ""

    try:
        credential = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
    except Exception:
        return ""

    value = credential.get("CredentialBlob")
    if isinstance(value, bytes):
        return value.decode("utf-16-le").rstrip("\x00")
    return str(value or "")


def _delete_legacy_windows_secret(key: str) -> bool:
    target = _target_for_key(key)
    try:
        import win32cred
    except ImportError:
        return False

    try:
        win32cred.CredDelete(target, win32cred.CRED_TYPE_GENERIC, 0)
        return True
    except Exception:
        return False


def _target_for_key(key: str) -> str:
    if key not in SECRET_KEYS:
        supported = ", ".join(sorted(SECRET_KEYS))
        raise ValueError(f"Unsupported secret {key!r}. Supported secrets: {supported}")
    return SECRET_KEYS[key]
