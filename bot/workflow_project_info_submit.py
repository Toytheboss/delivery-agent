"""Reply to a verification result in Lark with ``Project info submit``.

Official X and mainnet contract go to the wallet table. A tweet URL goes to
the progress-tracker KPI 2 field. A missing wallet row is created only when
X or a contract was sent.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bot.lark_bitable import create_record, get_tenant_access_token, list_records, update_record
from bot.workflow_form_dispatch import _field_text, _normalize_name
from bot.workflow_kpi1_twitter import _RESERVED_HANDLES, twitter_handle_from_url
from bot.workflow_kpi_write import extract_contract
from bot.workflow_lark_relay import claim_message
from bot.workflow_pr_capture import (
    _display_pr_url,
    collect_urls_from_text,
    is_tweet_url,
    kpi2_pass_fields,
)
from bot.workflow_tech_support import _extract_text_from_lark_content, _lark_creds

logger = logging.getLogger(__name__)

_CMD_RE = re.compile(
    r"(?is)^\s*(?:@_user_\d+\s*)*(?:[/@])?project\s+info\s+submit\b(.*)$"
)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_HANDLE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_]{1,15})\b")
_NAME_FIELD = "Project name"
_CONTRACT_FIELD = "Mainnet Contract Addresss"
_TWITTER_FIELD = "Link of Project X ( Formerly Twitter) Profile Page"
_DEFAULT_PROGRESS_NAME = "项目名称 Project Name"
_DEFAULT_KPI2_FIELD = "KPI 2 - PR 新闻链接验证"


def is_project_info_submit(text: str) -> bool:
    return bool(_CMD_RE.match((text or "").strip()))


def strip_command(text: str) -> str:
    match = _CMD_RE.match((text or "").strip())
    if not match:
        return (text or "").strip()
    return str(match.group(1) or "").strip()


def clean_project_label(raw: str) -> str:
    text = (raw or "").strip().strip("*` ").strip()
    linked = _MD_LINK_RE.fullmatch(text)
    if linked:
        return (linked.group(1) or "").strip()
    return text


def project_name_from_quoted(text: str) -> str:
    for line in (text or "").splitlines():
        plain = line.replace("*", "").strip()
        if plain.lower().startswith("project:"):
            return clean_project_label(plain.split(":", 1)[1])
    return ""


def parse_submit_payload(text: str) -> tuple[str, str, str]:
    """Return (contract, twitter_profile_url, pr_url). Empty when missing."""
    blob = _MD_LINK_RE.sub(lambda match: match.group(2), text or "")
    contract = extract_contract(blob)
    twitter = ""
    pr = ""
    for url in collect_urls_from_text(blob):
        if is_tweet_url(url):
            if not pr:
                pr = _display_pr_url(url)
            continue
        handle = twitter_handle_from_url(url)
        if handle and handle.lower() not in _RESERVED_HANDLES and not twitter:
            twitter = f"https://x.com/{handle}"
    if not twitter:
        bare = re.sub(r"https?://\S+", " ", blob, flags=re.IGNORECASE)
        found = _HANDLE_RE.search(bare)
        if found and found.group(1).lower() not in _RESERVED_HANDLES:
            twitter = f"https://x.com/{found.group(1)}"
    return contract, twitter, pr


def _expected_chat_id(config: Any) -> str:
    raw = getattr(config, "raw", {}) or {}
    workflow = raw.get("workflow") if isinstance(raw, dict) else {}
    block = (workflow or {}).get("project_info_submit") or {}
    if isinstance(block, dict):
        custom = str(block.get("lark_chat_id") or "").strip()
        if custom:
            return custom
    return str(getattr(config, "workflow_live_onboard_lark_chat_id", "") or "").strip()


def _enabled(config: Any) -> bool:
    raw = getattr(config, "raw", {}) or {}
    workflow = raw.get("workflow") if isinstance(raw, dict) else {}
    block = (workflow or {}).get("project_info_submit") or {}
    if isinstance(block, dict) and "enabled" in block:
        return bool(block.get("enabled"))
    return True


def message_text(message: dict[str, Any]) -> str:
    msg_type = str(message.get("message_type") or message.get("msg_type") or "text")
    raw = message.get("content")
    if raw is None:
        body = message.get("body") or {}
        raw = body.get("content") if isinstance(body, dict) else ""
    if isinstance(raw, dict):
        import json

        raw = json.dumps(raw, ensure_ascii=False)
    return _extract_text_from_lark_content(msg_type, str(raw or ""))


def _name_hits(
    rows: list[dict[str, Any]], project_name: str, name_field: str
) -> list[tuple[str, dict[str, Any]]]:
    key = _normalize_name(project_name)
    hits: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        if not rid or not isinstance(fields, dict):
            continue
        if _normalize_name(_field_text(fields, name_field)) != key:
            continue
        hits.append((rid, fields))
    return hits


def upsert_wallet_row(
    token: str,
    config: Any,
    *,
    project_name: str,
    contract: str,
    twitter: str,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    table_id = str(getattr(config, "workflow_wallet_table_id", "") or "").strip()
    name_field = str(
        getattr(config, "workflow_wallet_name_field", "") or _NAME_FIELD
    ).strip()
    if not app_token or not table_id:
        return {"ok": False, "reason": "wallet_table_not_configured"}
    if not contract and not twitter:
        return {"ok": True, "action": "skipped", "project": project_name, "record_ids": []}
    if rows is None:
        rows = list_records(token, app_token, table_id)
    hits = _name_hits(rows, project_name, name_field)
    payload: dict[str, str] = {}
    if contract:
        payload[_CONTRACT_FIELD] = contract
    if twitter:
        payload[_TWITTER_FIELD] = twitter
    if not hits:
        created = create_record(
            token,
            app_token,
            table_id,
            {name_field: project_name, **payload},
        )
        logger.info(
            "project info submit created wallet project=%r record=%s",
            project_name,
            created,
        )
        return {
            "ok": True,
            "action": "created",
            "project": project_name,
            "record_ids": [created],
            "contract": contract,
            "twitter": twitter,
        }
    updated: list[str] = []
    for rid, _fields in hits:
        update_record(token, app_token, table_id, rid, payload)
        updated.append(rid)
    logger.info(
        "project info submit updated wallet project=%r n=%s",
        project_name,
        len(updated),
    )
    return {
        "ok": True,
        "action": "updated",
        "project": project_name,
        "record_ids": updated,
        "contract": contract,
        "twitter": twitter,
        "duplicate_rows": len(updated) > 1,
    }


def write_pr_link(
    token: str,
    config: Any,
    *,
    project_name: str,
    pr_url: str,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not pr_url:
        return {"ok": True, "action": "skipped", "project": project_name, "record_ids": []}
    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    table_id = str(getattr(config, "workflow_progress_table_id", "") or "").strip()
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or _DEFAULT_PROGRESS_NAME
    ).strip()
    link_field = str(
        getattr(config, "pr_capture_link_field", "") or _DEFAULT_KPI2_FIELD
    ).strip()
    if not app_token or not table_id or not link_field:
        return {"ok": False, "reason": "progress_table_not_configured", "project": project_name}
    if rows is None:
        rows = list_records(token, app_token, table_id)
    hits = _name_hits(rows, project_name, name_field)
    if not hits:
        return {"ok": False, "reason": "progress_missing", "project": project_name, "pr": pr_url}
    updated: list[str] = []
    fields = kpi2_pass_fields(link_field=link_field, url=pr_url)
    for rid, _row_fields in hits:
        update_record(token, app_token, table_id, rid, fields)
        updated.append(rid)
    logger.info(
        "project info submit wrote PR project=%r n=%s", project_name, len(updated)
    )
    return {
        "ok": True,
        "action": "updated",
        "project": project_name,
        "record_ids": updated,
        "pr": pr_url,
        "duplicate_rows": len(updated) > 1,
    }


def format_submit_reply(
    *,
    project: str,
    wallet: dict[str, Any] | None = None,
    pr: dict[str, Any] | None = None,
    reason: str = "",
) -> str:
    if reason == "no_quote":
        return "Reply to the project result post, then send `Project info submit`."
    if reason == "no_project":
        return "Quoted message has no **Project:** line, so nothing was written."
    if reason == "empty_payload":
        return (
            "Send the X profile, mainnet contract (0x…), and/or the PR tweet "
            "link in the same message as `Project info submit`."
        )
    name = project or "this project"
    lines: list[str] = []
    wallet = wallet or {}
    pr = pr or {}
    if wallet.get("action") == "created":
        lines.append(f"Created info form row for {name}.")
    elif wallet.get("action") == "updated":
        lines.append(f"Updated info form row for {name}.")
    elif wallet.get("reason"):
        lines.append(f"{name}: info form write failed ({wallet['reason']}).")
    if wallet.get("twitter"):
        lines.append(f"Twitter: {wallet['twitter']}")
    if wallet.get("contract"):
        lines.append(f"Contract: {wallet['contract']}")
    if wallet.get("duplicate_rows"):
        count = len(wallet.get("record_ids") or [])
        lines.append(
            f"Note: {count} info form rows share this name. "
            "Merge them later so KPI checks can match."
        )
    if pr.get("ok") and pr.get("action") == "updated":
        lines.append("PR written to KPI 2.")
        if pr.get("pr"):
            lines.append(str(pr["pr"]))
        if pr.get("duplicate_rows"):
            count = len(pr.get("record_ids") or [])
            lines.append(f"Note: {count} progress rows share this name.")
    elif pr.get("reason") == "progress_missing":
        lines.append(f"PR was not written: no progress row for {name}.")
    elif pr.get("reason"):
        lines.append(f"PR was not written ({pr['reason']}).")
    if not lines:
        return f"{name}: nothing was written."
    return "\n".join(lines)


def _reply(token: str, message_id: str, text: str) -> None:
    from bot.workflow_lark_bridge import _reply_to_message

    _reply_to_message(token, message_id, text)


def maybe_handle_project_info_submit(
    config: Any, event_data: dict[str, Any]
) -> dict[str, Any] | None:
    """Handle Project info submit in the verification group. None = not this command."""
    if not _enabled(config):
        return None
    if not isinstance(event_data, dict):
        return None
    message = event_data.get("message") or {}
    sender = event_data.get("sender") or {}
    if not isinstance(message, dict):
        return None
    if str(sender.get("sender_type") or "").lower() == "app":
        return None
    expected = _expected_chat_id(config)
    chat_id = str(message.get("chat_id") or "").strip()
    if not expected or chat_id != expected:
        return None
    text = message_text(message)
    if not is_project_info_submit(text):
        return None

    from bot.lark_bitable import LarkBitableError
    from bot.workflow_lark_recall import get_message

    message_id = str(message.get("message_id") or "")
    if not claim_message(message_id):
        return {"ok": True, "project_info_submit": "duplicate"}

    app_id, app_secret = _lark_creds(config)
    if not app_id or not app_secret:
        logger.error("project info submit missing Lark credentials")
        return {"ok": False, "project_info_submit": "no_credentials"}
    try:
        token = get_tenant_access_token(app_id, app_secret)
    except Exception:
        logger.exception("project info submit token failed")
        return {"ok": False, "project_info_submit": "token_failed"}

    parent_id = str(message.get("parent_id") or message.get("root_id") or "").strip()
    if not parent_id:
        _reply(token, message_id, format_submit_reply(project="", reason="no_quote"))
        return {"ok": True, "project_info_submit": "no_quote"}

    try:
        parent = get_message(token, parent_id) or {}
    except Exception:
        logger.exception("project info submit get parent failed")
        _reply(token, message_id, "Could not read the quoted result post. Try again.")
        return {"ok": False, "project_info_submit": "parent_missing"}

    quoted = message_text(parent if isinstance(parent, dict) else {})
    project = project_name_from_quoted(quoted)
    if not project:
        _reply(token, message_id, format_submit_reply(project="", reason="no_project"))
        return {"ok": True, "project_info_submit": "no_project"}

    contract, twitter, pr_url = parse_submit_payload(strip_command(text))
    if not contract and not twitter and not pr_url:
        _reply(
            token,
            message_id,
            format_submit_reply(project=project, reason="empty_payload"),
        )
        return {"ok": True, "project_info_submit": "empty_payload"}

    wallet: dict[str, Any] = {"ok": True, "action": "skipped"}
    pr: dict[str, Any] = {"ok": True, "action": "skipped"}
    try:
        if contract or twitter:
            wallet = upsert_wallet_row(
                token,
                config,
                project_name=project,
                contract=contract,
                twitter=twitter,
            )
        if pr_url:
            pr = write_pr_link(token, config, project_name=project, pr_url=pr_url)
    except LarkBitableError:
        logger.exception("project info submit write failed project=%r", project)
        _reply(token, message_id, f"{project}: table write failed.")
        return {"ok": False, "project_info_submit": "write_failed"}

    if pr.get("ok") and pr.get("action") == "updated":
        try:
            from bot.workflow_pr_weekly import log_capture_event

            for rid in pr.get("record_ids") or []:
                log_capture_event(
                    config,
                    record_id=str(rid),
                    project=project,
                    url=str(pr.get("pr") or pr_url),
                )
        except Exception:
            logger.exception("project info submit failed to log PR event")

    reply = format_submit_reply(project=project, wallet=wallet, pr=pr)
    _reply(token, message_id, reply)
    try:
        from bot.workflow_events import log_delivery

        log_delivery(
            "project_info_submit",
            "Project info submit",
            project_name=project,
            text=reply.replace("\n", " · "),
            record_id=(wallet.get("record_ids") or pr.get("record_ids") or [""])[0],
        )
    except Exception:
        pass
    return {
        "ok": True,
        "project_info_submit": "done",
        "project": project,
        "wallet": wallet.get("action"),
        "pr": pr.get("action") if pr.get("ok") else pr.get("reason"),
    }
