"""TG keyword → update Lark Progress Tracker status to live (+ optional form send)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.folder_scope import FolderScope
from bot.lark_bitable import get_tenant_access_token, list_records, update_record
from bot.workflow_form_dispatch import (
    _field_text,
    _normalize_name,
    _parse_chat_id,
    is_manual_form_command,
    match_project_to_chat,
)
from bot.workflow_live_trigger import process_live_project

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PENDING_PATH = ROOT / "data" / "mark_live_pending.json"
PENDING_TTL_SECONDS = 24 * 3600


@dataclass
class MarkLiveOutcome:
    text: str
    candidates: list[tuple[str, str]] | None = None  # (record_id, project_name)


def is_mark_live_command(text: str, commands: list[str]) -> bool:
    return is_manual_form_command(text, commands)


def _pending_key(chat_id: int, reply_msg_id: int) -> str:
    return f"{chat_id}:{reply_msg_id}"


def _load_pending() -> dict[str, Any]:
    if not PENDING_PATH.exists():
        return {"by_reply": {}}
    try:
        raw = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"by_reply": {}}
    if not isinstance(raw, dict):
        return {"by_reply": {}}
    by_reply = raw.get("by_reply")
    if not isinstance(by_reply, dict):
        by_reply = {}
    return {"by_reply": by_reply}


def _save_pending(state: dict[str, Any]) -> None:
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PENDING_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(PENDING_PATH)


def _prune_pending(state: dict[str, Any], *, now: float | None = None) -> None:
    now = time.time() if now is None else now
    by_reply = state.setdefault("by_reply", {})
    dead = [
        key
        for key, entry in list(by_reply.items())
        if not isinstance(entry, dict) or float(entry.get("expires_at") or 0) <= now
    ]
    for key in dead:
        by_reply.pop(key, None)


def save_mark_live_pending(
    *,
    chat_id: int,
    reply_msg_id: int,
    chat_title: str,
    candidates: list[tuple[str, str]],
) -> None:
    """Persist ambiguous candidates keyed by the bot reply message id."""
    now = time.time()
    state = _load_pending()
    _prune_pending(state, now=now)
    state["by_reply"][_pending_key(chat_id, reply_msg_id)] = {
        "chat_id": int(chat_id),
        "chat_title": chat_title,
        "candidates": [
            {"record_id": rid, "project_name": name} for rid, name in candidates
        ],
        "created_at": now,
        "expires_at": now + PENDING_TTL_SECONDS,
    }
    _save_pending(state)


def pop_mark_live_pending(chat_id: int, reply_msg_id: int) -> dict[str, Any] | None:
    now = time.time()
    state = _load_pending()
    _prune_pending(state, now=now)
    key = _pending_key(chat_id, reply_msg_id)
    entry = state["by_reply"].pop(key, None)
    if entry is not None:
        _save_pending(state)
    if not isinstance(entry, dict):
        return None
    if int(entry.get("chat_id") or 0) != int(chat_id):
        return None
    return entry


def peek_mark_live_pending(chat_id: int, reply_msg_id: int) -> dict[str, Any] | None:
    now = time.time()
    state = _load_pending()
    _prune_pending(state, now=now)
    entry = state["by_reply"].get(_pending_key(chat_id, reply_msg_id))
    if not isinstance(entry, dict):
        return None
    if int(entry.get("chat_id") or 0) != int(chat_id):
        return None
    return entry


def _pick_candidate(
    picked_name: str,
    candidates: list[tuple[str, str]],
) -> tuple[str, str] | None | list[tuple[str, str]]:
    """Return (record_id, name), None if no match, or list if still ambiguous."""
    want = _normalize_name(picked_name)
    if not want:
        return None

    exact = [(rid, name) for rid, name in candidates if _normalize_name(name) == want]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return exact

    partial = [
        (rid, name)
        for rid, name in candidates
        if want in _normalize_name(name) or _normalize_name(name) in want
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        return partial
    return None


def _ambiguous_text(matches: list[tuple[str, str]]) -> str:
    names = ", ".join(name for _, name in matches)
    return (
        f"Ambiguous match ({len(matches)}): {names}.\n"
        "Quote this message and reply with the exact project name to continue."
    )


async def _maybe_write_tg_chat_id(
    loop: asyncio.AbstractEventLoop,
    token: str,
    config: AppConfig,
    *,
    record_id: str,
    fields: dict[str, Any],
    chat_id: int,
) -> str | None:
    field = (config.workflow_tg_chat_id_field or "").strip()
    if not field:
        return None
    existing = _parse_chat_id(_field_text(fields, field))
    if existing == chat_id:
        return None
    try:
        await loop.run_in_executor(
            None,
            update_record,
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            record_id,
            {field: str(chat_id)},
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "mark_live: failed writing tg chat id field=%r record=%s chat=%s",
            field,
            record_id,
            chat_id,
        )
        return f"Could not save TG chat id to Lark field {field!r}."
    logger.info(
        "mark_live: wrote tg chat id field=%r record=%s chat=%s",
        field,
        record_id,
        chat_id,
    )
    return f"Saved TG chat id {chat_id} to Lark."


async def _apply_mark_live(
    client: TelegramClient,
    config: AppConfig,
    *,
    token: str,
    record_id: str,
    project_name: str,
    fields: dict[str, Any],
    chat_id: int,
    chat_title: str,
) -> str:
    loop = asyncio.get_running_loop()
    old_status = _field_text(fields, config.workflow_status_field)
    new_status = config.workflow_trigger_status

    if old_status == new_status:
        logger.info(
            "Mark-live skipped Lark update: project=%r record=%s already %r chat=%s",
            project_name,
            record_id,
            new_status,
            chat_id,
        )
        lines = [
            f"Lark already live: {project_name}",
            f"Status: {new_status}",
        ]
    else:
        try:
            await loop.run_in_executor(
                None,
                update_record,
                token,
                config.workflow_base_app_token,
                config.workflow_progress_table_id,
                record_id,
                {config.workflow_status_field: new_status},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("mark_live: failed to update Lark status")
            return f"Matched {project_name!r} but failed to update Lark: {exc}"

        logger.info(
            "Marked live via TG: project=%r record=%s %r -> %r chat=%s",
            project_name,
            record_id,
            old_status,
            new_status,
            chat_id,
        )
        lines = [
            f"Lark updated: {project_name}",
            f"Status: {old_status or '(empty)'} → {new_status}",
        ]

    note = await _maybe_write_tg_chat_id(
        loop,
        token,
        config,
        record_id=record_id,
        fields=fields,
        chat_id=chat_id,
    )
    if note:
        lines.append(note)

    if config.workflow_mark_live_also_send_form or config.workflow_logo_fill_enabled:
        scope = FolderScope(client, config)
        await scope.refresh()
        outcome = await process_live_project(
            client,
            config,
            scope,
            record_id=record_id,
            project_name=project_name,
            require_live_status=True,
            source="mark_live",
            preferred_chat_id=chat_id,
            preferred_chat_title=chat_title,
        )
        form = outcome.get("form")
        if form == "sent":
            lines.append(
                f"Google Form sent to {outcome.get('chat_title') or 'matched group'}."
            )
        elif form == "already_sent":
            lines.append("Google Form already sent earlier (skipped).")
        elif form and str(form).startswith("no_group"):
            lines.append(f"Status updated, but no TG group match ({form}).")
        elif form and form not in {"skipped", "no_form_url"}:
            lines.append(f"Form result: {form}")

        logo_status = str(outcome.get("logo") or "")
        if logo_status.startswith("ok"):
            lines.append("Project logo uploaded to Lark.")
        elif logo_status in {"already_has_logo", "already_processed", "baseline_has_logo"}:
            lines.append("Project logo already set (skipped).")
        elif logo_status in {"disabled", "skipped"}:
            pass
        else:
            lines.append(f"Logo fill skipped/failed ({logo_status}); will not retry.")

    return "\n".join(lines)


def _collect_matches(
    config: AppConfig,
    records: list[dict[str, Any]],
    chat_id: int,
    chat_title: str,
) -> list[tuple[str, str, dict[str, Any]]]:
    """Prefer exact TG chat id field matches; else fuzzy title matches."""
    id_matches: list[tuple[str, str, dict[str, Any]]] = []
    field = (config.workflow_tg_chat_id_field or "").strip()
    if field:
        for record in records:
            record_id = str(record.get("record_id") or "")
            fields = record.get("fields") or {}
            project_name = _field_text(fields, config.workflow_project_name_field)
            if not record_id or not project_name:
                continue
            stored = _parse_chat_id(_field_text(fields, field))
            if stored == chat_id:
                id_matches.append((record_id, project_name, fields))
        if id_matches:
            return id_matches

    title_map = {chat_id: chat_title}
    matches: list[tuple[str, str, dict[str, Any]]] = []
    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        project_name = _field_text(fields, config.workflow_project_name_field)
        if not record_id or not project_name:
            continue
        matched, _reason = match_project_to_chat(project_name, title_map)
        if matched == chat_id:
            matches.append((record_id, project_name, fields))
    return matches


async def mark_live_from_group(
    client: TelegramClient,
    config: AppConfig,
    chat_id: int,
    chat_title: str,
) -> MarkLiveOutcome:
    """Match current TG group to a Lark project and set status to live."""
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return MarkLiveOutcome("Missing LARK_APP_ID / LARK_APP_SECRET in .env")

    if not chat_title.strip():
        return MarkLiveOutcome("Cannot resolve this group title.")

    loop = asyncio.get_running_loop()
    try:
        token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
        records = await loop.run_in_executor(
            None,
            list_records,
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("mark_live: failed to load Lark records")
        return MarkLiveOutcome(f"Failed to read Lark: {exc}")

    matches = _collect_matches(config, records, chat_id, chat_title)

    if not matches:
        return MarkLiveOutcome(
            f"No Lark project matched this group title ({chat_title!r}). "
            "Align Progress Tracker「项目名称」with the TG group name."
        )
    if len(matches) > 1:
        candidates = [(rid, name) for rid, name, _fields in matches]
        return MarkLiveOutcome(_ambiguous_text(candidates), candidates=candidates)

    record_id, project_name, fields = matches[0]
    text = await _apply_mark_live(
        client,
        config,
        token=token,
        record_id=record_id,
        project_name=project_name,
        fields=fields,
        chat_id=chat_id,
        chat_title=chat_title,
    )
    return MarkLiveOutcome(text)


async def resolve_mark_live_reply(
    client: TelegramClient,
    config: AppConfig,
    *,
    chat_id: int,
    chat_title: str,
    quoted_msg_id: int,
    picked_text: str,
) -> str | None:
    """If quote targets an ambiguous mark-live prompt, continue with picked name.

    Returns reply text when handled, or None when this is not a pending prompt.
    """
    pending = peek_mark_live_pending(chat_id, quoted_msg_id)
    if pending is None:
        return None

    raw_candidates = pending.get("candidates") or []
    candidates: list[tuple[str, str]] = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("record_id") or "").strip()
        name = str(item.get("project_name") or "").strip()
        if rid and name:
            candidates.append((rid, name))
    if not candidates:
        pop_mark_live_pending(chat_id, quoted_msg_id)
        return "Ambiguous mark-live prompt expired or empty. Run mark live again."

    picked = (picked_text or "").strip()
    if not picked:
        return (
            "Reply with the exact project name, e.g. "
            + (candidates[0][1] if candidates else "Project Name")
        )

    choice = _pick_candidate(picked, candidates)
    if choice is None:
        names = ", ".join(name for _, name in candidates)
        return (
            f"No match for {picked!r} among: {names}.\n"
            "Quote the Ambiguous message again and reply with the exact name."
        )
    if isinstance(choice, list):
        names = ", ".join(name for _, name in choice)
        return (
            f"Still ambiguous ({len(choice)}): {names}.\n"
            "Quote again and reply with the exact project name."
        )

    record_id, project_name = choice
    # Consume pending only after a unique pick so typos can retry.
    pop_mark_live_pending(chat_id, quoted_msg_id)

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return "Missing LARK_APP_ID / LARK_APP_SECRET in .env"

    loop = asyncio.get_running_loop()
    try:
        token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
        records = await loop.run_in_executor(
            None,
            list_records,
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("mark_live resolve: failed to load Lark records")
        return f"Failed to read Lark: {exc}"

    fields: dict[str, Any] = {}
    for record in records:
        if str(record.get("record_id") or "") == record_id:
            fields = record.get("fields") or {}
            live_name = _field_text(fields, config.workflow_project_name_field)
            if live_name:
                project_name = live_name
            break
    else:
        return f"Lark record {record_id} no longer found. Run mark live again."

    title = (chat_title or "").strip() or str(pending.get("chat_title") or "")
    return await _apply_mark_live(
        client,
        config,
        token=token,
        record_id=record_id,
        project_name=project_name,
        fields=fields,
        chat_id=chat_id,
        chat_title=title,
    )
