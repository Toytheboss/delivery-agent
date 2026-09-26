"""Telegram group commands that run one KPI check and write Lark.

`onchain diag` / `twitter diag` / `website diag` / `project diag` —
send in the project group, no quote. Enabled only on Roy号.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records, update_record
from bot.workflow_form_chase import field_is_filled
from bot.workflow_kpi_write import field_result
from bot.workflow_pr_capture import _collect_matches

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.custom.message import Message

    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

_DIAG_RE = re.compile(
    r"(?is)^\s*(?:[/@])?(onchain|twitter|website|project)\s+diag\s*[!.。！]*\s*$"
)
_KIND_LABEL = {
    "onchain": "KPI 6 on-chain",
    "twitter": "KPI 1 Twitter",
    "website": "KPI 3 website",
    "project": "Project diag",
}
_PASS = "通过"
_COORD_FIELD = "KPI 统筹"
_KPI2_LINK = "KPI 2 - PR 新闻链接验证"
_KPI2_RESULT = "新闻验证结果"
_KPI4_RESULT = "产品可用验证结果"
_KPI5_RESULT = "独立性验证结果"


def parse_kpi_diag_command(text: str) -> str | None:
    match = _DIAG_RE.match(text or "")
    if not match:
        return None
    return match.group(1).lower()


def is_kpi_diag_command(text: str) -> bool:
    return parse_kpi_diag_command(text) is not None


def _cell_passed(fields: dict[str, Any], result_field: str) -> bool:
    return field_result(fields, result_field) == _PASS


def twitter_fail_note(outcome: dict[str, Any]) -> str:
    reason = str(outcome.get("reason") or "")
    if reason == "no_account":
        return "no official account"
    if reason == "unread":
        return "unread"
    count = outcome.get("count")
    if reason == "below_threshold" or (isinstance(count, int) and count < 5):
        n = 0 if count is None else int(count)
        return f"{n} original posts in 30 days, need ≥5"
    return reason or "failed"


def onchain_fail_note(outcome: dict[str, Any]) -> str:
    reason = str(outcome.get("reason") or "")
    if reason == "no_contract":
        return "no contract"
    wallets = int(outcome.get("wallets") or 0)
    txs = int(outcome.get("txs") or 0)
    return f"{wallets} wallets / {txs} txs, need ≥3 wallets and ≥5 txs"


def website_fail_note(outcome: dict[str, Any]) -> str:
    reason = str(outcome.get("reason") or "")
    if reason == "no_url":
        return "no site URL"
    if reason == "unreachable":
        return "unreachable"
    if reason in {"missing_official_link", "no_name_or_logo"}:
        return "missing official links"
    return reason or "failed"


def pr_status(fields: dict[str, Any]) -> tuple[bool, str]:
    if _cell_passed(fields, _KPI2_RESULT) or field_is_filled(fields, _KPI2_LINK):
        return True, ""
    return False, "no news URL"


def format_project_diag_reply(
    *,
    project: str,
    rows: list[tuple[str, bool, str]],
    coord_written: bool,
) -> str:
    failed_names = [name for name, passed, _note in rows if not passed]
    overall = "passed" if not failed_names else "failed"
    lines = [f"Project diag for {project}: {overall}"]
    if failed_names:
        lines.append("Failed: " + ", ".join(failed_names))
    for name, passed, note in rows:
        if passed:
            lines.append(f"{name}: passed")
        elif note:
            lines.append(f"{name}: failed ({note})")
        else:
            lines.append(f"{name}: failed")
    lines.append(
        "Coordination: passed" if coord_written else "Coordination: not written"
    )
    return "\n".join(lines)


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
        elif reason == "below_threshold":
            extra = f" ({onchain_fail_note(outcome)})"
    elif kind == "twitter":
        handle = outcome.get("handle") or ""
        extra = f" @{handle}" if handle else " (no account)"
        if reason == "unread":
            extra += " unread"
        elif reason == "below_threshold":
            extra = f" ({twitter_fail_note(outcome)})"
    return f"{label} written for {project!r}: {result}{extra}"


def _write_coordination(token: str, config: AppConfig, record_id: str) -> None:
    payload = {_COORD_FIELD: _PASS}
    try:
        update_record(
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            record_id,
            payload,
        )
    except Exception:
        update_record(
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            record_id,
            {_COORD_FIELD: "有效 KPI"},
        )


async def _run_one(
    loop: asyncio.AbstractEventLoop,
    kind: str,
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    project_name: str,
) -> dict[str, Any]:
    if kind == "onchain":
        from bot.workflow_kpi6_onchain import audit_kpi6_for_fields

        return await loop.run_in_executor(
            None,
            lambda: audit_kpi6_for_fields(
                token, config, record_id, fields, project_name=project_name
            ),
        )
    if kind == "twitter":
        from bot.workflow_kpi1_twitter import audit_kpi1_for_fields

        return await loop.run_in_executor(
            None,
            lambda: audit_kpi1_for_fields(
                token, config, record_id, fields, project_name=project_name
            ),
        )
    from bot.workflow_kpi3_website import audit_kpi3_for_fields

    out = await loop.run_in_executor(
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
    if isinstance(out, dict):
        return out
    return {"result": str(out), "reason": str(out), "project": project_name}


async def _run_project_diag(
    loop: asyncio.AbstractEventLoop,
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    project_name: str,
) -> str:
    twitter = await _run_one(
        loop, "twitter", token, config, record_id, fields, project_name
    )
    website = await _run_one(
        loop, "website", token, config, record_id, fields, project_name
    )
    onchain = await _run_one(
        loop, "onchain", token, config, record_id, fields, project_name
    )
    kpi2_ok, kpi2_note = pr_status(fields)
    kpi4_ok = _cell_passed(fields, _KPI4_RESULT)
    kpi5_ok = _cell_passed(fields, _KPI5_RESULT)
    kpi1_ok = bool(twitter.get("passed") or twitter.get("result") == _PASS)
    kpi3_ok = bool(website.get("passed") or website.get("result") == _PASS)
    kpi6_ok = bool(onchain.get("passed") or onchain.get("result") == _PASS)
    rows = [
        ("KPI 1 Twitter", kpi1_ok, "" if kpi1_ok else twitter_fail_note(twitter)),
        ("KPI 2 PR", kpi2_ok, kpi2_note),
        ("KPI 3 Website", kpi3_ok, "" if kpi3_ok else website_fail_note(website)),
        ("KPI 4 Product", kpi4_ok, "" if kpi4_ok else "not passed"),
        ("KPI 5 Independence", kpi5_ok, "" if kpi5_ok else "not passed"),
        ("KPI 6 On-chain", kpi6_ok, "" if kpi6_ok else onchain_fail_note(onchain)),
    ]
    all_ok = all(passed for _n, passed, _note in rows)
    coord_written = False
    if all_ok:
        try:
            await loop.run_in_executor(
                None, lambda: _write_coordination(token, config, record_id)
            )
            coord_written = True
        except Exception as exc:  # noqa: BLE001
            logger.exception("kpi_diag: coordination write failed record=%s", record_id)
            return (
                format_project_diag_reply(
                    project=project_name, rows=rows, coord_written=False
                )
                + f"\nCoordination write failed: {exc}"
            )
    return format_project_diag_reply(
        project=project_name, rows=rows, coord_written=coord_written
    )


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
        if kind == "project":
            return await _run_project_diag(
                loop, token, config, record_id, fields, project_name
            )
        outcome = await _run_one(
            loop, kind, token, config, record_id, fields, project_name
        )
        if kind == "website" and outcome.get("result") in {
            "write_failed",
            "disabled",
            "no_record",
        }:
            return f"Matched {project_name!r} but website diag: {outcome.get('result')}"
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "kpi_diag: %s failed project=%r record=%s", kind, project_name, record_id
        )
        return f"Matched {project_name!r} but KPI diag failed: {exc}"
    return _reply_for(kind, outcome)
