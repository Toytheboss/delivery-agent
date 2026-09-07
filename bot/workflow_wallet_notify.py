"""Workflow step 8: wallet table complete → notify finance / ops / tech."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.workflow_form_dispatch import (
    _field_text,
    _normalize_name,
    build_folder_title_map,
)

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


def _load_notified(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(x) for x in (raw.get("notified_record_ids") or [])}


def _save_notified(path: Path, ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"notified_record_ids": sorted(ids)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _wallet_complete(fields: dict[str, Any], required: list[str]) -> bool:
    for name in required:
        if not _field_text(fields, name):
            return False
    return True


def _format_wallet_notice(fields: dict[str, Any], field_names: list[str]) -> str:
    project = _field_text(fields, "Project name") or "Unknown project"
    lines = [f"[Wallet form completed] {project}", ""]
    for name in field_names:
        value = _field_text(fields, name)
        if value:
            lines.append(f"{name}: {value}")
    return "\n".join(lines)


def _title_matches_notify_target(title: str, wanted: set[str]) -> bool:
    """Match internal notify groups by normalized exact title only.

    Substring matching is unsafe inside Delivery folders: e.g. ``ops`` hits
    ``FaucetDrops``, ``tech`` hits ``Votechain``, ``finance`` hits partner
    groups whose names merely contain that word.
    """
    nt = _normalize_name(title)
    if not nt:
        return False
    return nt in wanted


async def _resolve_notify_chats(
    client: TelegramClient,
    scope: FolderScope,
    config: AppConfig,
) -> list[int]:
    chats: list[int] = []
    chats.extend(int(x) for x in config.workflow_notify_chat_ids)

    if not config.workflow_notify_group_titles:
        return sorted(set(chats))

    if not scope.chat_ids:
        await scope.refresh()
    title_map = await build_folder_title_map(client, scope.chat_ids)
    wanted = {
        _normalize_name(t)
        for t in config.workflow_notify_group_titles
        if _normalize_name(t)
    }
    matched_titles: list[str] = []
    for chat_id, title in title_map.items():
        if _title_matches_notify_target(title, wanted):
            chats.append(chat_id)
            matched_titles.append(title)
    if config.workflow_notify_group_titles and not matched_titles:
        logger.warning(
            "wallet notify: no Folder chat exact-matched notify_group_titles=%s; "
            "set workflow.notify_chat_ids to the real Finance/Ops/Tech chat ids",
            config.workflow_notify_group_titles,
        )
    elif matched_titles:
        logger.info(
            "wallet notify: title-matched chats=%s",
            matched_titles,
        )
    return sorted(set(chats))


async def run_wallet_notify_once(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> int:
    if not config.workflow_enabled or not config.workflow_wallet_notify_enabled:
        return 0

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("wallet notify skipped: missing LARK credentials")
        return 0

    notify_chats = await _resolve_notify_chats(client, scope, config)
    if not notify_chats:
        logger.warning(
            "wallet notify: no notify chats configured "
            "(set workflow.notify_chat_ids or notify_group_titles)"
        )
        return 0

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_wallet_table_id,
    )

    state_path = ROOT / config.workflow_wallet_notify_state_file
    notified = _load_notified(state_path)
    if config.workflow_baseline_existing_live and not state_path.exists():
        for record in records:
            rid = str(record.get("record_id") or "")
            fields = record.get("fields") or {}
            if rid and _wallet_complete(fields, config.workflow_wallet_required_fields):
                notified.add(rid)
        _save_notified(state_path, notified)
        logger.info(
            "Wallet notify baseline: marked %d complete record(s) as already notified",
            len(notified),
        )
        return 0

    sent = 0
    dirty = False
    display_fields = list(
        dict.fromkeys(
            ["Project name"]
            + config.workflow_wallet_required_fields
            + [
                "Fee Collector / Revenue Wallet Address",
                "Multi-sig Threshold (Optional)",
                "Grant Receiving Wallet (Optional)",
                "MM / LP Wallet （Optional）",
                "Bridge Pool / Relayer Wallet (Optional)",
            ]
        )
    )

    for record in records:
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in notified:
            continue
        fields = record.get("fields") or {}
        if not _wallet_complete(fields, config.workflow_wallet_required_fields):
            continue

        text = _format_wallet_notice(fields, display_fields)
        ok_any = False
        for chat_id in notify_chats:
            try:
                await client.send_message(chat_id, text)
                ok_any = True
            except Exception:
                logger.exception("Failed wallet notify to chat_id=%s", chat_id)
        if ok_any:
            notified.add(record_id)
            dirty = True
            sent += 1
            logger.info(
                "Wallet notify sent for %r record=%s to %s chat(s)",
                _field_text(fields, "Project name"),
                record_id,
                len(notify_chats),
            )

    if dirty or not state_path.exists():
        _save_notified(state_path, notified)
    return sent


async def wallet_notify_loop(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> None:
    interval = max(config.workflow_poll_interval_minutes, 1) * 60
    while True:
        try:
            n = await run_wallet_notify_once(client, config, scope)
            if n:
                logger.info("Wallet notify cycle sent %d notice(s)", n)
        except Exception:
            logger.exception("Wallet notify cycle failed")
        await asyncio.sleep(interval)
