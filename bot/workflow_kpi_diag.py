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

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.workflow_form_chase import field_is_filled
from bot.workflow_kpi45_live import _KPI4_COPY, _KPI5_COPY, fill_kpi45_for_fields
from bot.workflow_kpi_pass_chain import (
    KPI7_PASS_COPY,
    apply_pass_chain,
    coord_is_pass,
    planned_kpi2_result,
    write_kpi2_result,
)
from bot.workflow_kpi_write import (
    diag_not_eligible_reason,
    field_result,
)
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
    "onchain": "On-chain",
    "twitter": "Twitter",
    "website": "Website",
    "project": "Project diag",
}
_PASS = "通过"
_KPI1_RESULT = "推特验证结果"
_KPI2_LINK = "KPI 2 - PR 新闻链接验证"
_KPI2_RESULT = "新闻验证结果"
_KPI3_RESULT = "官网验证结果"
_KPI4_RESULT = "产品可用验证结果"
_KPI5_RESULT = "独立性验证结果"
_KPI6_RESULT = "交互验证结果"
_KPI7_RESULT = "持续运营要求验证结果"
_KPI2_PASS = (
    "News/PR verification: a news URL was submitted; news/PR verification passed"
)
_KPI2_FAIL = (
    "News/PR verification: missing PR news link; news/PR verification failed"
)
_KPI7_COPY = KPI7_PASS_COPY
_KPI7_OPEN = (
    "Ongoing operations verification: not passed (earlier checks still have open items)"
)
_SKIPPED_COPY = {
    "twitter": "Twitter operations verification: already passed",
    "website": "Website display verification: already passed",
    "onchain": "User and interaction verification: already passed",
}


def parse_kpi_diag_command(text: str) -> str | None:
    match = _DIAG_RE.match(text or "")
    if not match:
        return None
    return match.group(1).lower()


def is_kpi_diag_command(text: str) -> bool:
    return parse_kpi_diag_command(text) is not None


def _cell_passed(fields: dict[str, Any], result_field: str) -> bool:
    return field_result(fields, result_field) == _PASS


def already_passed(fields: dict[str, Any], result_field: str) -> bool:
    return _cell_passed(fields, result_field)


def skipped_pass(project_name: str, kind: str) -> dict[str, Any]:
    return {
        "passed": True,
        "result": _PASS,
        "reason": "already",
        "skipped": True,
        "copy": _SKIPPED_COPY.get(kind, "already passed"),
        "project": project_name,
    }


def project_diag_audits_to_run(fields: dict[str, Any]) -> list[str]:
    """Expensive checks still needed. Same skip rule as a later first/second official audit."""
    kinds: list[str] = []
    if not already_passed(fields, _KPI1_RESULT):
        kinds.append("twitter")
    if not already_passed(fields, _KPI3_RESULT):
        kinds.append("website")
    if not already_passed(fields, _KPI6_RESULT):
        kinds.append("onchain")
    return kinds


def latest_copy(copy: str) -> str:
    text = (copy or "").strip()
    marker = "\nRecheck "
    if marker in text:
        tail = text.rsplit(marker, 1)[-1]
        if ": " in tail:
            return tail.split(": ", 1)[1].strip() or text
    return text


def twitter_fail_note(outcome: dict[str, Any]) -> str:
    copy = latest_copy(str(outcome.get("copy") or ""))
    if copy:
        return copy
    reason = str(outcome.get("reason") or "")
    if reason == "no_account":
        return (
            "Twitter operations verification: no official account submitted; "
            "Twitter operations verification failed"
        )
    if reason == "unread":
        return (
            "Twitter operations verification: official account could not be "
            "read for original posts in the last 30 days; "
            "Twitter operations verification failed"
        )
    count = outcome.get("count")
    if reason == "below_threshold" or (isinstance(count, int) and count < 5):
        n = 0 if count is None else int(count)
        return (
            f"Twitter operations verification: official account posted {n} "
            "original posts in the last 30 days (threshold ≥5); "
            "Twitter operations verification failed"
        )
    return reason or "Twitter operations verification failed"


def onchain_fail_note(outcome: dict[str, Any]) -> str:
    copy = latest_copy(str(outcome.get("copy") or ""))
    if copy:
        return copy
    reason = str(outcome.get("reason") or "")
    if reason == "no_contract":
        return (
            "User and interaction verification: no contract detected; "
            "user and interaction verification failed"
        )
    wallets = int(outcome.get("wallets") or 0)
    txs = int(outcome.get("txs") or 0)
    return (
        f"User and interaction verification: {wallets} unique wallets, "
        f"{txs} successful core txs (threshold ≥3 wallets and ≥5 txs); "
        "user and interaction verification failed"
    )


def website_fail_note(outcome: dict[str, Any]) -> str:
    copy = latest_copy(str(outcome.get("copy") or ""))
    if copy:
        return copy
    reason = str(outcome.get("reason") or "")
    if reason == "no_url":
        return (
            "Website display verification: no official website URL submitted; "
            "website display verification failed"
        )
    if reason == "unreachable":
        return (
            "Website display verification: website could not be opened; "
            "website display verification failed"
        )
    if reason == "no_botchain_name":
        return (
            "Website display verification: website opened, BOT Chain name not found; "
            "website display verification failed"
        )
    if reason in {"missing_official_link", "no_name_or_logo"}:
        return (
            "Website display verification: website opened, missing official links; "
            "website display verification failed"
        )
    return reason or "Website display verification failed"


def pr_status(fields: dict[str, Any]) -> tuple[bool, str]:
    if _cell_passed(fields, _KPI2_RESULT) or field_is_filled(fields, _KPI2_LINK):
        return True, _KPI2_PASS
    return False, _KPI2_FAIL


def format_project_diag_reply(
    *,
    project: str,
    rows: list[tuple[str, bool, str]],
    coord_written: bool,
    skipped: bool = False,
) -> str:
    if skipped:
        return (
            f"Project diag for {project}: skipped\n"
            "Final evaluation already passed."
        )
    failed = [(name, note) for name, passed, note in rows if not passed]
    passed = [(name, note) for name, passed, note in rows if passed]
    overall = "passed" if not failed else "failed"
    lines = [f"Project diag for {project}: {overall}", ""]
    if failed:
        lines.append("Failed")
        for name, note in failed:
            lines.append(f"{name}: {note}" if note else f"{name}: failed")
        lines.append("")
    if passed:
        lines.append("Passed")
        for name, note in passed:
            lines.append(f"{name}: {note}" if note else f"{name}: passed")
        lines.append("")
    lines.append(
        "Final evaluation: passed" if coord_written else "Final evaluation: not written"
    )
    return "\n".join(lines).rstrip()


def _reply_for(kind: str, outcome: dict[str, Any]) -> str:
    project = outcome.get("project") or "this project"
    result = outcome.get("result") or "不通过"
    label = _KIND_LABEL.get(kind, kind)
    copy = str(outcome.get("copy") or "").strip()
    result_en = {"通过": "passed", "不通过": "failed"}.get(str(result), str(result))
    if copy:
        return f"{label} written for {project!r}: {result_en}\n{copy}"
    reason = outcome.get("reason") or ""
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
    return f"{label} written for {project!r}: {result_en}{extra}"


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
    kpi4_ok = _cell_passed(fields, _KPI4_RESULT)
    kpi5_ok = _cell_passed(fields, _KPI5_RESULT)
    if not kpi4_ok or not kpi5_ok:
        filled = "write_failed"
        try:
            filled = await loop.run_in_executor(
                None,
                lambda: fill_kpi45_for_fields(
                    token, config, record_id, fields, project_name=project_name
                ),
            )
        except Exception:
            logger.exception("kpi_diag: KPI 4/5 backfill failed record=%s", record_id)
        if filled in {_PASS, "already_filled"}:
            kpi4_ok = True
            kpi5_ok = True
            fields = {
                **fields,
                _KPI4_RESULT: _PASS,
                _KPI5_RESULT: _PASS,
            }

    if coord_is_pass(fields):
        try:
            await loop.run_in_executor(
                None, lambda: apply_pass_chain(token, config, record_id, fields)
            )
        except Exception:
            logger.exception("kpi_diag: pass-chain after KPI 4/5 failed record=%s", record_id)
        return format_project_diag_reply(
            project=project_name, rows=[], coord_written=True, skipped=True
        )

    to_run = set(project_diag_audits_to_run(fields))
    if "twitter" in to_run:
        twitter = await _run_one(
            loop, "twitter", token, config, record_id, fields, project_name
        )
        pr_url = str(twitter.get("pr_url") or "").strip()
        if pr_url:
            fields = {**fields, _KPI2_LINK: pr_url, _KPI2_RESULT: _PASS}
    else:
        logger.info("kpi_diag: skip twitter already passed project=%s", project_name)
        twitter = skipped_pass(project_name, "twitter")
        from bot.workflow_kpi1_twitter import fill_kpi2_pr_from_twitter

        try:
            pr_url = await loop.run_in_executor(
                None,
                lambda: fill_kpi2_pr_from_twitter(
                    token, config, record_id, fields, project_name=project_name
                ),
            )
        except Exception:
            logger.exception("kpi_diag: PR tweet fill failed record=%s", record_id)
            pr_url = ""
        if pr_url:
            fields = {**fields, _KPI2_LINK: pr_url, _KPI2_RESULT: _PASS}

    kpi2_write = planned_kpi2_result(fields)
    if kpi2_write:
        try:
            await loop.run_in_executor(
                None, lambda: write_kpi2_result(token, config, record_id, kpi2_write)
            )
            fields = {**fields, _KPI2_RESULT: kpi2_write}
        except Exception:
            logger.exception("kpi_diag: KPI 2 write failed record=%s", record_id)

    if "website" in to_run:
        website = await _run_one(
            loop, "website", token, config, record_id, fields, project_name
        )
    else:
        logger.info("kpi_diag: skip website already passed project=%s", project_name)
        website = skipped_pass(project_name, "website")
    if "onchain" in to_run:
        onchain = await _run_one(
            loop, "onchain", token, config, record_id, fields, project_name
        )
    else:
        logger.info("kpi_diag: skip onchain already passed project=%s", project_name)
        onchain = skipped_pass(project_name, "onchain")
    kpi2_ok, kpi2_note = pr_status(fields)
    kpi1_ok = bool(twitter.get("passed") or twitter.get("result") == _PASS)
    kpi3_ok = bool(website.get("passed") or website.get("result") == _PASS)
    kpi6_ok = bool(onchain.get("passed") or onchain.get("result") == _PASS)
    kpi7_ok = already_passed(fields, _KPI7_RESULT)
    first_six_ok = kpi1_ok and kpi2_ok and kpi3_ok and kpi4_ok and kpi5_ok and kpi6_ok
    overlay = dict(fields)
    if kpi1_ok:
        overlay[_KPI1_RESULT] = _PASS
    if kpi2_ok:
        overlay[_KPI2_RESULT] = _PASS
    if kpi3_ok:
        overlay[_KPI3_RESULT] = _PASS
    overlay[_KPI4_RESULT] = _PASS
    overlay[_KPI5_RESULT] = _PASS
    if kpi6_ok:
        overlay[_KPI6_RESULT] = _PASS
    coord_written = False
    if first_six_ok:
        try:
            await loop.run_in_executor(
                None, lambda: apply_pass_chain(token, config, record_id, overlay)
            )
            kpi7_ok = True
            coord_written = True
        except Exception as exc:  # noqa: BLE001
            logger.exception("kpi_diag: pass-chain write failed record=%s", record_id)
            rows = _project_diag_rows(
                kpi1_ok,
                twitter,
                kpi2_ok,
                kpi2_note,
                kpi3_ok,
                website,
                kpi4_ok,
                kpi5_ok,
                kpi6_ok,
                onchain,
                False,
            )
            return (
                format_project_diag_reply(
                    project=project_name, rows=rows, coord_written=False
                )
                + f"\nFinal evaluation write failed: {exc}"
            )
    rows = _project_diag_rows(
        kpi1_ok,
        twitter,
        kpi2_ok,
        kpi2_note,
        kpi3_ok,
        website,
        kpi4_ok,
        kpi5_ok,
        kpi6_ok,
        onchain,
        kpi7_ok,
    )
    return format_project_diag_reply(
        project=project_name, rows=rows, coord_written=coord_written
    )


def _project_diag_rows(
    kpi1_ok: bool,
    twitter: dict[str, Any],
    kpi2_ok: bool,
    kpi2_note: str,
    kpi3_ok: bool,
    website: dict[str, Any],
    kpi4_ok: bool,
    kpi5_ok: bool,
    kpi6_ok: bool,
    onchain: dict[str, Any],
    kpi7_ok: bool,
) -> list[tuple[str, bool, str]]:
    if kpi1_ok:
        kpi1_note = latest_copy(str(twitter.get("copy") or "")) or _SKIPPED_COPY["twitter"]
    else:
        kpi1_note = twitter_fail_note(twitter)
    if kpi3_ok:
        kpi3_note = latest_copy(str(website.get("copy") or "")) or _SKIPPED_COPY["website"]
    else:
        kpi3_note = website_fail_note(website)
    if kpi6_ok:
        kpi6_note = latest_copy(str(onchain.get("copy") or "")) or _SKIPPED_COPY["onchain"]
    else:
        kpi6_note = onchain_fail_note(onchain)
    kpi7_note = _KPI7_COPY if kpi7_ok else _KPI7_OPEN
    return [
        ("Twitter", kpi1_ok, kpi1_note),
        ("News/PR", kpi2_ok, kpi2_note),
        ("Website", kpi3_ok, kpi3_note),
        ("Product", kpi4_ok, _KPI4_COPY),
        ("Independence", kpi5_ok, _KPI5_COPY),
        ("On-chain", kpi6_ok, kpi6_note),
        ("Ongoing operations", kpi7_ok, kpi7_note),
    ]


async def run_kpi_diag(
    client: TelegramClient,
    config: AppConfig,
    command_message: Message,
    chat_id: int,
    chat_title: str,
) -> str:
    del client
    if not getattr(config, "workflow_kpi_diag_enabled", False):
        return "This check is disabled on this bot."
    kind = parse_kpi_diag_command(getattr(command_message, "raw_text", None) or "")
    if not kind:
        return "Unknown diag command."

    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    table_id = str(getattr(config, "workflow_progress_table_id", "") or "").strip()
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_token or not table_id:
        return "Project diag is not configured."
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
            "Not running this check until the group maps to one project."
        )

    record_id, project_name, fields = matches[0]
    status_field = str(getattr(config, "workflow_status_field", "") or "项目状态")
    blocked = diag_not_eligible_reason(fields, status_field)
    if blocked:
        return blocked
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
        return f"Matched {project_name!r} but the check failed: {exc}"
    return _reply_for(kind, outcome)
