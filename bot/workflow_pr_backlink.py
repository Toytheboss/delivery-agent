"""Send a PR-table backlink to that project's Telegram group.

Lark automation on 「项目方PR链接推送」 calls the webhook when 回链 changes.
There is no poll. The same URL on the same row is not sent again. A different
URL on that row is sent again. The same URL on another row still goes to that
other project's group.

The frontend weekly table is ignored. Disabled until
workflow.pr_backlink.enabled is true.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_TABLE_ID = "tbllA25Mz66e8wpv"
_FRONTEND_TABLE_ID = "tblsPBJW1HUmkM6X"
_BACKLINK_FIELD_ID = "fldvWXObg6"
_NAME_FIELD = "项目方"
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s<>\]]+", re.IGNORECASE)


def plain_url(text: str) -> str:
    """First http(s) URL in a cell. Empty when the cell has no link."""
    raw = (text or "").strip()
    if not raw:
        return ""
    match = _MD_LINK_RE.search(raw) or _URL_RE.search(raw)
    if not match:
        return ""
    return match.group(1).rstrip(").,，。>") if match.re is _MD_LINK_RE else match.group(0).rstrip(").,，。>")


def _cell_text(fields: dict[str, Any], name: str) -> str:
    value = fields.get(name)
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or item))
            else:
                parts.append(str(item))
        return " ".join(parts).strip()
    return str(value).strip()


def backlink_text(fields: dict[str, Any]) -> str:
    for key in fields:
        if str(key).startswith("回链"):
            return _cell_text(fields, str(key))
    return ""


def pending_backlinks(records: list[dict[str, Any]], sent: dict[str, str]) -> list[dict[str, str]]:
    """Rows whose 回链 URL is new for that row. Other columns are ignored."""
    pending: list[dict[str, str]] = []
    for record in records:
        record_id = str(record.get("record_id") or "").strip()
        fields = record.get("fields") or {}
        if not record_id or not isinstance(fields, dict):
            continue
        url = plain_url(backlink_text(fields))
        project = _cell_text(fields, _NAME_FIELD)
        if not url or not project:
            continue
        if sent.get(record_id) == url:
            continue
        pending.append({"record_id": record_id, "project": project, "url": url})
    return pending


def _normalize_name(text: str) -> str:
    return re.sub(r"[^\w]+", "", str(text or "").lower().strip(), flags=re.UNICODE)


def _parse_chat_id(raw: str) -> int | None:
    text = (raw or "").strip().replace(" ", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _progress_matches(
    project: str,
    progress_records: list[dict[str, Any]],
    name_field: str,
) -> list[dict[str, Any]]:
    needle = _normalize_name(project)
    if not needle:
        return []
    found = []
    for record in progress_records:
        fields = record.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        if _normalize_name(_cell_text(fields, name_field)) == needle:
            found.append(record)
    return found


def resolve_project_chat(
    project: str,
    progress_records: list[dict[str, Any]],
    title_by_chat: dict[int, str],
    *,
    name_field: str,
    chat_field: str,
    title_matcher: Any = None,
) -> tuple[int | None, str]:
    """Progress-table TG id first, then the folder group title."""
    matches = _progress_matches(project, progress_records, name_field)
    chat_ids: list[int] = []
    if chat_field:
        for record in matches:
            parsed = _parse_chat_id(_cell_text(record.get("fields") or {}, chat_field))
            if parsed is not None:
                chat_ids.append(parsed)
    unique = list(dict.fromkeys(chat_ids))
    if len(unique) == 1:
        return unique[0], "progress TG id"
    if len(unique) > 1:
        return None, f"ambiguous TG ids: {unique}"
    if title_matcher is None:
        from bot.workflow_form_dispatch import match_project_to_chat

        title_matcher = match_project_to_chat
    chat_id, reason = title_matcher(project, title_by_chat)
    return chat_id, reason


def _state_path(config: Any) -> Path:
    override = str(getattr(config, "pr_backlink_state_file", "") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else ROOT / path
    shared = Path("/opt/botchain-shared/pr_backlink_state.json")
    if shared.parent.is_dir():
        return shared
    return ROOT / "data" / "pr_backlink_state.json"


def load_sent(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    sent = raw.get("sent") if isinstance(raw, dict) else None
    if not isinstance(sent, dict):
        return {}
    return {str(key): str(value) for key, value in sent.items() if str(key) and str(value)}


def save_sent(path: Path, sent: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"sent": sent}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def dispatch_backlinks(
    client: Any,
    pending: list[dict[str, str]],
    progress_records: list[dict[str, Any]],
    title_by_chat: dict[int, str],
    sent: dict[str, str],
    *,
    name_field: str,
    chat_field: str,
    dry_run: bool = False,
    title_matcher: Any = None,
) -> list[dict[str, Any]]:
    """Send each pending URL. Failed or unmatched rows stay unsent."""
    results: list[dict[str, Any]] = []
    for item in pending:
        chat_id, reason = resolve_project_chat(
            item["project"],
            progress_records,
            title_by_chat,
            name_field=name_field,
            chat_field=chat_field,
            title_matcher=title_matcher,
        )
        outcome: dict[str, Any] = {
            "record_id": item["record_id"],
            "project": item["project"],
            "url": item["url"],
            "chat_id": chat_id,
            "reason": reason,
            "sent": False,
        }
        if chat_id is None:
            logger.warning(
                "pr backlink skip %r (%s): %s",
                item["project"],
                item["record_id"],
                reason,
            )
            results.append(outcome)
            continue
        if dry_run:
            outcome["dry_run"] = True
            results.append(outcome)
            continue
        try:
            await client.send_message(chat_id, item["url"])
        except Exception:
            logger.exception(
                "pr backlink send failed project=%r chat=%s",
                item["project"],
                chat_id,
            )
            outcome["reason"] = "send failed"
            results.append(outcome)
            continue
        sent[item["record_id"]] = item["url"]
        outcome["sent"] = True
        logger.info(
            "pr backlink sent project=%r chat=%s url=%s",
            item["project"],
            chat_id,
            item["url"][:120],
        )
        results.append(outcome)
    return results


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("text") or value.get("link") or value.get("url") or "")
    if isinstance(value, list):
        return " ".join(_as_text(item) for item in value)
    return str(value)


def _table_id_of(data: dict[str, Any]) -> str:
    for key in ("table_id", "tableId"):
        if data.get(key):
            return str(data.get(key)).strip()
    event = data.get("event")
    if isinstance(event, dict) and event.get("table_id"):
        return str(event.get("table_id")).strip()
    return ""


def _named_url(obj: dict[str, Any]) -> str:
    for key, value in obj.items():
        name = str(key)
        if name.startswith("回链") or name in {"url", "backlink", "link"}:
            found = plain_url(_as_text(value))
            if found:
                return found
    fields = obj.get("fields")
    if isinstance(fields, dict):
        return _named_url(fields)
    return ""


def _named_project(obj: dict[str, Any]) -> str:
    for key in ("项目方", "project", "project_name", "projectName"):
        if obj.get(key):
            return _as_text(obj.get(key)).strip()
    fields = obj.get("fields")
    if isinstance(fields, dict):
        return _named_project(fields)
    return ""


def _from_record_event(event: dict[str, Any]) -> dict[str, str] | None:
    """Pull a 回链 edit out of a bitable record-changed event. Other fields are ignored."""
    for action in event.get("action_list") or []:
        if not isinstance(action, dict):
            continue
        record_id = str(action.get("record_id") or "").strip()
        for change in action.get("after_value") or []:
            if not isinstance(change, dict):
                continue
            field_id = str(change.get("field_id") or "")
            field_name = str(change.get("field_name") or "")
            if field_id != _BACKLINK_FIELD_ID and not field_name.startswith("回链"):
                continue
            url = plain_url(_as_text(change.get("field_value")))
            if record_id or url:
                return {"record_id": record_id, "project": "", "url": url}
    return None


def parse_backlink_trigger(data: dict[str, Any]) -> dict[str, str] | None:
    """One doorbell. None means this request is not a backlink on the PR table."""
    if not isinstance(data, dict):
        return None
    table_id = _table_id_of(data)
    if table_id == _FRONTEND_TABLE_ID or (table_id and table_id != _DEFAULT_TABLE_ID):
        return None
    event = data.get("event")
    if isinstance(event, dict) and event.get("action_list"):
        if str(event.get("table_id") or table_id or "") not in {"", _DEFAULT_TABLE_ID}:
            return None
        found = _from_record_event(event)
        if not found:
            return None
        return found
    record_id = str(data.get("record_id") or data.get("recordId") or "").strip()
    url = _named_url(data)
    project = _named_project(data)
    if not record_id and not url:
        return None
    return {"record_id": record_id, "project": project, "url": url}


async def handle_backlink_trigger(
    client: Any,
    config: Any,
    scope: Any,
    data: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send the URL from one Lark automation call. Does not scan the table."""
    if not getattr(config, "pr_backlink_enabled", False) and not dry_run:
        return {"ok": True, "skipped": True, "reason": "disabled"}
    parsed = parse_backlink_trigger(data)
    if not parsed:
        return {"ok": True, "ignored": True, "reason": "not_backlink"}

    from bot.lark_bitable import get_tenant_access_token, list_records
    from bot.workflow_form_dispatch import build_folder_title_map

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    table_id = str(getattr(config, "pr_backlink_table_id", "") or _DEFAULT_TABLE_ID).strip()
    progress_id = str(getattr(config, "workflow_progress_table_id", "") or "").strip()
    if not app_id or not app_secret or not app_token or not table_id or not progress_id:
        logger.warning("pr backlink missing Lark credentials or table ids")
        return {"ok": False, "skipped": True, "reason": "not_configured"}

    record = {
        "record_id": parsed["record_id"] or "trigger",
        "fields": {_NAME_FIELD: parsed["project"], "回链": parsed["url"]},
    }
    if not parsed["url"] and parsed["record_id"]:
        loop = asyncio.get_running_loop()
        token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
        rows = await loop.run_in_executor(None, list_records, token, app_token, table_id)
        record = next(
            (row for row in rows if str(row.get("record_id") or "") == parsed["record_id"]),
            None,
        )
        if record is None:
            return {"ok": True, "ignored": True, "reason": "record_not_found"}

    path = _state_path(config)
    sent = load_sent(path)
    pending = pending_backlinks([record], sent)
    if not pending:
        return {"ok": True, "pending": 0, "reason": "unchanged"}

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    progress = await loop.run_in_executor(None, list_records, token, app_token, progress_id)
    title_by_chat: dict[int, str] = {}
    if scope is not None and client is not None:
        title_by_chat = await build_folder_title_map(client, scope.chat_ids())
    results = await dispatch_backlinks(
        client,
        pending,
        progress,
        title_by_chat,
        sent,
        name_field=str(
            getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
        ),
        chat_field=str(getattr(config, "workflow_tg_chat_id_field", "") or ""),
        dry_run=dry_run,
    )
    if not dry_run:
        save_sent(path, sent)
    sent_ok = any(item.get("sent") for item in results)
    return {"ok": True, "pending": len(pending), "sent": sent_ok, "results": results}
