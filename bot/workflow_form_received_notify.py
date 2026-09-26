"""When the Google onboarding form is in Lark, ping Project verification push."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.lark_im import send_markdown_post_to_chat
from bot.workflow_form_chase import (
    DEFAULT_CHASE_FIELDS,
    _chase_fields,
    _find_wallet_fields,
    count_filled_fields,
)
from bot.workflow_form_dispatch import _field_text, match_project_to_chat
from bot.workflow_live_onboard import parse_bd_person, sends_lark_notify

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
_LAST_SCAN = 0.0
_MIN_SCAN_GAP = 90.0


def build_form_received_message(
    *,
    project: str,
    group: str,
    bd_name: str,
    bd_open_id: str,
) -> str:
    at = (
        f'<at user_id="{bd_open_id}">{bd_name or "BD"}</at>'
        if bd_open_id
        else f"@{bd_name or 'BD'}"
    )
    project_label = (project or "Unknown project").strip() or "Unknown project"
    group_label = (group or "not matched").strip() or "not matched"
    return (
        f"{at}\n\n"
        f"**Project:** `{project_label}`\n"
        f"**Status:** Google Onboarding form received\n"
        f"**TG group:** `{group_label}`\n"
        f"**Form:** Submitted; Twitter, contract, logo and intro are in Lark\n\n"
        "No action needed. Delivery Agent will pick this up in the midnight wallet digest"
    )


def _state_path(config: Any) -> Path:
    override = str(
        getattr(config, "workflow_form_received_notify_state_file", "") or ""
    ).strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else ROOT / path
    shared = Path("/opt/botchain-shared/form_received_notify_state.json")
    if shared.parent.is_dir():
        return shared
    return ROOT / "data" / "form_received_notify_state.json"


def _load_notified(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(x) for x in (raw.get("notified_record_ids") or []) if str(x)}


def _save_notified(path: Path, notified: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"notified_record_ids": sorted(notified)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _load_title_cache() -> dict[int, str]:
    out: dict[int, str] = {}
    seen: set[str] = set()
    candidates = [
        Path("/opt/botchain-qa-tg-bot/data/folder_title_cache.json"),
        Path("/opt/delivery-agent/data/folder_title_cache.json"),
        ROOT / "data" / "folder_title_cache.json",
    ]
    for path in candidates:
        try:
            if not path.is_file():
                continue
            key = str(path.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(raw, dict):
            continue
        entries = raw.get("titles") if isinstance(raw.get("titles"), dict) else raw
        if not isinstance(entries, dict):
            continue
        for chat_key, entry in entries.items():
            try:
                chat_id = int(chat_key)
            except (TypeError, ValueError):
                continue
            title = (
                str(entry.get("title") or "").strip()
                if isinstance(entry, dict)
                else str(entry or "").strip()
            )
            if title:
                out[chat_id] = title
    return out


def _matched_group_title(project_name: str, titles: dict[int, str]) -> str:
    chat_id, _reason = match_project_to_chat(project_name, titles)
    if chat_id is None:
        return ""
    return str(titles.get(chat_id) or "").strip()


def _send_one(
    config: Any,
    *,
    project: str,
    group: str,
    fields: dict[str, Any],
) -> str:
    chat_id = str(getattr(config, "workflow_live_onboard_lark_chat_id", "") or "").strip()
    if not chat_id:
        return "skipped_no_chat"
    bd_field = str(getattr(config, "workflow_live_onboard_bd_field", "") or "BD")
    bd_open_id, bd_name = parse_bd_person(fields, bd_field)
    text = build_form_received_message(
        project=project,
        group=group,
        bd_name=bd_name,
        bd_open_id=bd_open_id,
    )
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return "skipped_no_lark_creds"
    token = get_tenant_access_token(app_id, app_secret)
    send_markdown_post_to_chat(token, chat_id, text)
    logger.info(
        "form-received notified project=%r bd=%s group=%r",
        project,
        bd_name,
        group,
    )
    try:
        from bot.workflow_events import append_event

        append_event(
            "form_received_notified",
            "form_received_notify",
            project_name=project,
            text=f"{project} 的 Google 表单已回收，已推 Project verification push",
            status="success",
        )
    except Exception:  # noqa: BLE001
        pass
    return "sent"


async def run_form_received_notify_once(config: Any) -> int:
    """Baseline existing complete forms; notify only newly completed live rows."""
    global _LAST_SCAN
    if not getattr(config, "workflow_form_received_notify_enabled", True):
        return 0
    if not sends_lark_notify(config):
        return 0
    if not str(getattr(config, "workflow_live_onboard_lark_chat_id", "") or "").strip():
        return 0

    now = time.time()
    path = _state_path(config)
    first_run = not path.exists()
    if not first_run and now - _LAST_SCAN < _MIN_SCAN_GAP:
        return 0
    _LAST_SCAN = now

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return 0

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    progress = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
    )
    wallet_records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_wallet_table_id,
    )
    fields_needed = _chase_fields(config) or list(DEFAULT_CHASE_FIELDS)
    required = max(len(fields_needed), 1)
    name_field = str(
        getattr(config, "workflow_project_name_field", "项目名称 Project Name")
        or "项目名称 Project Name"
    )
    status_field = str(getattr(config, "workflow_status_field", "") or "")
    live_status = str(getattr(config, "workflow_trigger_status", "") or "")
    titles = _load_title_cache()
    notified = _load_notified(path)
    complete_ids: set[str] = set()
    pending: list[tuple[str, str, str, dict[str, Any]]] = []

    for record in progress:
        rid = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        if not rid:
            continue
        if status_field and live_status:
            if _field_text(fields, status_field) != live_status:
                continue
        name = _field_text(fields, name_field)
        if not name:
            continue
        wallet_fields = _find_wallet_fields(
            wallet_records, name, fields_needed=fields_needed
        )
        filled = count_filled_fields(wallet_fields or {}, fields_needed)
        if filled < required:
            continue
        complete_ids.add(rid)
        if rid in notified:
            continue
        group = _matched_group_title(name, titles)
        pending.append((rid, name, group, fields))

    if first_run:
        notified |= complete_ids
        _save_notified(path, notified)
        logger.info(
            "form-received baseline: marked %d complete live row(s) (no send)",
            len(complete_ids),
        )
        return 0

    sent = 0
    for rid, name, group, fields in pending:
        try:
            result = _send_one(config, project=name, group=group, fields=fields)
        except Exception:
            logger.exception("form-received notify failed project=%r (%s)", name, rid)
            continue
        if result == "sent":
            notified.add(rid)
            sent += 1
            _save_notified(path, notified)
    return sent
