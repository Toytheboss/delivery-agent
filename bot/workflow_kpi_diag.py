"""Telegram group commands that run one KPI check and write Lark.

`onchain diag` / `twitter diag` / `website diag` — send in the project group,
no quote. Enabled only on Roy号 via workflow.kpi_diag.enabled.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.workflow_pr_capture import _collect_matches

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.custom.message import Message

    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

_DIAG_RE = re.compile(
    r"(?is)^\s*(?:[/@])?(onchain|twitter|website)\s+diag\s*[!.。！]*\s*$"
)
_KIND_LABEL = {
    "onchain": "KPI 6 on-chain",
    "twitter": "KPI 1 Twitter",
    "website": "KPI 3 website",
}


def parse_kpi_diag_command(text: str) -> str | None:
    match = _DIAG_RE.match(text or "")
    if not match:
        return None
    return match.group(1).lower()


def is_kpi_diag_command(text: str) -> bool:
    return parse_kpi_diag_command(text) is not None


def _reply_for(kind: str, outcome: dict[str, Any]) -> str:
    project = outcome.get("project") or "this project"
    result = outcome.get("result") or "不通过"
    reason = outcome.get("reason") or ""
    label = _KIND_LABEL.get(kind, kind)
    extra = ""
    if kind == "onchain":
        extra = f" wallets={outcome.get('wallets', 0)} txs={outcome.get('txs', 0)}"
        if reason == "no_contract":
            extra = " (no contract)"
    elif kind == "twitter":
        handle = outcome.get("handle") or ""
        extra = f" @{handle}" if handle else " (no account)"
        if reason == "unread":
            extra += " unread"
    return f"{label} written for {project!r}: {result}{extra}"


async def run_kpi_diag(
    client: TelegramClient,
    config: AppConfig,
    command_message: Message,
    chat_id: int,
    chat_title: str,
) -> str:
    del client
    if not getattr(config, "workflow_kpi_diag_enabled", False):
        return "KPI diag is disabled on this bot."
    kind = parse_kpi_diag_command(getattr(command_message, "raw_text", None) or "")
    if not kind:
        return "Unknown KPI diag command."

    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    table_id = str(getattr(config, "workflow_progress_table_id", "") or "").strip()
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_token or not table_id:
        return "KPI diag is not configured."
    if not app_id or not app_secret:
        return "Missing LARK_APP_ID / LARK_APP_SECRET in .env"

    loop = asyncio.get_running_loop()
    try:
        token = await loop.run_in_executor(
            None, get_tenant_access_token, app_id, app_secret
        )
        records = await loop.run_in_executor(
            None, list_records, token, app_token, table_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("kpi_diag: failed to read Lark chat=%s", chat_id)
        return f"Failed to read Lark: {exc}"

    matches = _collect_matches(config, records, chat_id, chat_title)
    if not matches:
        return (
            f"No Lark project matched this group title ({chat_title!r}). "
            "Align Progress Tracker project name with the TG group name."
        )
    if len(matches) > 1:
        names = ", ".join(name for _rid, name, _fields in matches)
        return (
            f"Ambiguous ({len(matches)} projects): {names}. "
            "Not running KPI diag until the group maps to one project."
        )

    record_id, project_name, fields = matches[0]
    try:
        if kind == "onchain":
            from bot.workflow_kpi6_onchain import audit_kpi6_for_fields

            outcome = await loop.run_in_executor(
                None,
                lambda: audit_kpi6_for_fields(
                    token, config, record_id, fields, project_name=project_name
                ),
            )
        elif kind == "twitter":
            from bot.workflow_kpi1_twitter import audit_kpi1_for_fields

            outcome = await loop.run_in_executor(
                None,
                lambda: audit_kpi1_for_fields(
                    token, config, record_id, fields, project_name=project_name
                ),
            )
        else:
            from bot.workflow_kpi3_website import audit_kpi3_for_fields

            status = await loop.run_in_executor(
                None,
                lambda: audit_kpi3_for_fields(
                    token,
                    config,
                    record_id,
                    fields,
                    project_name=project_name,
                    skip_if_audited=False,
                ),
            )
            if status in {"write_failed", "disabled", "no_record"}:
                return f"Matched {project_name!r} but website diag: {status}"
            outcome = {
                "result": status if status in {"通过", "不通过"} else str(status),
                "reason": str(status),
                "project": project_name,
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "kpi_diag: %s failed project=%r record=%s", kind, project_name, record_id
        )
        return f"Matched {project_name!r} but KPI diag failed: {exc}"
    return _reply_for(kind, outcome)
