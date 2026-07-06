from __future__ import annotations

import json
import base64
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig
from .models import EmailAttachment, SourceEmail

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def load_graph_emails(
    config: AppConfig,
    sender_contains: str | None = None,
    max_messages: int | None = None,
) -> list[SourceEmail]:
    token = get_graph_access_token(config)
    messages: list[SourceEmail] = []
    max_count = max_messages or (config.imap_max_messages if config.imap_max_messages > 0 else 500)
    remaining = max_count

    query = {
        "$top": str(min(50, remaining)),
        "$select": "id,internetMessageId,subject,from,sentDateTime,receivedDateTime,body,hasAttachments",
    }
    if sender_contains:
        query["$search"] = f'"from:{sender_contains}"'
    else:
        query["$orderby"] = "receivedDateTime desc"

    url = f"{GRAPH_ROOT}/me/messages?{urllib.parse.urlencode(query)}"
    print(
        f"Graph: fetching up to {max_count} message(s)"
        + (f" matching sender/search {sender_contains!r}" if sender_contains else ""),
        flush=True,
    )

    while url and remaining > 0:
        try:
            payload = _graph_get(url, token)
        except urllib.error.HTTPError as exc:
            if sender_contains and exc.code in {400, 501}:
                print("Graph: server-side sender search failed; falling back to recent-message scan.", flush=True)
                fallback_messages = load_graph_emails(config, sender_contains=None, max_messages=max_count)
                sender = sender_contains.lower()
                return [message for message in fallback_messages if sender in message.sender.lower()]
            raise
        for item in payload.get("value", []):
            if item.get("hasAttachments"):
                item["attachments"] = _load_graph_attachments(str(item["id"]), token)
            source = _source_from_graph_message(item)
            if _matches_since(source, config.search_since_days):
                if sender_contains and sender_contains.lower() not in source.sender.lower():
                    continue
                messages.append(source)
                remaining -= 1
                if remaining <= 0:
                    break
            else:
                return messages
        print(f"Graph: loaded {len(messages)} matching message(s).", flush=True)
        url = payload.get("@odata.nextLink")
    return messages


def get_graph_access_token(
    config: AppConfig,
    prompt_callback=None,
    scopes: list[str] | None = None,
) -> str:
    config.validate_graph()
    requested_scopes = scopes or config.graph_scopes
    try:
        import msal
    except ImportError as exc:
        raise RuntimeError(
            "Microsoft Graph auth requires msal. "
            "Install dependencies with: .\\.venv\\Scripts\\python.exe -m pip install -e ."
        ) from exc

    cache = msal.SerializableTokenCache()
    cache_path = config.graph_token_cache
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        client_id=config.graph_client_id,
        authority=f"https://login.microsoftonline.com/{config.graph_tenant}",
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(requested_scopes, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=requested_scopes)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to create Microsoft device-code flow: {flow}")
        if prompt_callback:
            prompt_callback(flow)
        else:
            print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    _persist_cache(cache, cache_path)

    if "access_token" not in result:
        error = result.get("error")
        description = result.get("error_description")
        raise RuntimeError(f"Microsoft Graph auth failed: {error}: {description}")

    return result["access_token"]


def _persist_cache(cache, cache_path: Path) -> None:
    if not cache.has_state_changed:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(cache.serialize(), encoding="utf-8")


def _graph_get(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Prefer": 'outlook.body-content-type="text"',
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _source_from_graph_message(item: dict) -> SourceEmail:
    from_info = item.get("from", {}).get("emailAddress", {})
    sender_name = from_info.get("name") or ""
    sender_address = from_info.get("address") or ""
    sender = f"{sender_name} <{sender_address}>" if sender_name and sender_address else sender_address
    sent_at = _parse_graph_datetime(item.get("sentDateTime") or item.get("receivedDateTime"))
    body = item.get("body", {}).get("content") or ""
    subject = item.get("subject") or ""
    message_id = item.get("internetMessageId") or item.get("id") or ""
    raw_bytes = "\n".join(
        [
            f"Message-ID: {message_id}",
            f"From: {sender}",
            f"Subject: {subject}",
            f"Date: {sent_at.isoformat() if sent_at else ''}",
            "",
            body,
        ]
    ).encode("utf-8", errors="replace")

    return SourceEmail(
        message_id=message_id,
        subject=subject,
        sender=sender,
        sent_at=sent_at,
        body_text=body,
        raw_bytes=raw_bytes,
        attachments=tuple(_source_attachments_from_graph(item)),
    )


def _load_graph_attachments(message_id: str, token: str) -> list[dict]:
    encoded_id = urllib.parse.quote(message_id, safe="")
    url = f"{GRAPH_ROOT}/me/messages/{encoded_id}/attachments"
    try:
        payload = _graph_get(url, token)
    except urllib.error.HTTPError:
        return []
    return payload.get("value", [])


def _source_attachments_from_graph(item: dict) -> list[EmailAttachment]:
    attachments: list[EmailAttachment] = []
    for attachment in item.get("attachments", []):
        content = attachment.get("contentBytes")
        if not content:
            continue
        try:
            decoded = base64.b64decode(content)
        except Exception:
            continue
        attachments.append(
            EmailAttachment(
                filename=attachment.get("name") or "",
                content_type=attachment.get("contentType") or "",
                content=decoded,
            )
        )
    return attachments


def _parse_graph_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _matches_since(source: SourceEmail, since_days: int) -> bool:
    if not source.sent_at:
        return True
    cutoff = datetime.now(timezone.utc).timestamp() - since_days * 24 * 60 * 60
    return source.sent_at.timestamp() >= cutoff
