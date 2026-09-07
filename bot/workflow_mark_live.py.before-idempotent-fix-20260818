"""TG keyword → update Lark Progress Tracker status to live (+ optional form send)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from bot.folder_scope import FolderScope
from bot.lark_bitable import get_tenant_access_token, list_records, update_record
from bot.workflow_form_dispatch import (
    _field_text,
    is_manual_form_command,
    match_project_to_chat,
)
from bot.workflow_live_trigger import process_live_project

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)


def is_mark_live_command(text: str, commands: list[str]) -> bool:
    return is_manual_form_command(text, commands)


async def mark_live_from_group(
    client: TelegramClient,
    config: AppConfig,
    chat_id: int,
    chat_title: str,
) -> str:
    """Match current TG group to a Lark project and set status to live."""
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return "Missing LARK_APP_ID / LARK_APP_SECRET in .env"

    if not chat_title.strip():
        return "Cannot resolve this group title."

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
        return f"Failed to read Lark: {exc}"

    title_map = {chat_id: chat_title}
    matches: list[tuple[str, str, dict[str, Any]]] = []
    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        project_name = _field_text(fields, config.workflow_project_name_field)
        if not record_id or not project_name:
            continue
        matched, reason = match_project_to_chat(project_name, title_map)
        if matched == chat_id:
            matches.append((record_id, project_name, fields))

    if not matches:
        return (
            f"No Lark project matched this group title ({chat_title!r}). "
            "Align Progress Tracker「项目名称」with the TG group name."
        )
    if len(matches) > 1:
        names = ", ".join(m[1] for m in matches)
        return f"Ambiguous match ({len(matches)}): {names}. Refine project/group names."

    record_id, project_name, fields = matches[0]
    old_status = _field_text(fields, config.workflow_status_field)
    new_status = config.workflow_trigger_status

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

    # Immediate form + logo (same path as Lark webhook; no polling)
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
