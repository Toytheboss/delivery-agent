"""Quote a TG PR message + `pr support` → overwrite official KPI 2 link field."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from bot.lark_bitable import get_tenant_access_token, list_records, update_record
from bot.lark_im import send_text_to_chat
from bot.project_logo import link_str
from bot.workflow_form_dispatch import (
    _field_text,
    _normalize_name,
    _parse_chat_id,
    is_manual_form_command,
    match_project_to_chat,
)
from bot.workflow_pr_weekly import log_capture_event

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.custom.message import Message

    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+", re.IGNORECASE)
_TWEET_HOSTS = frozenset(
    {"twitter.com", "x.com", "vxtwitter.com", "fxtwitter.com", "nitter.net"}
)
_RESERVED_HANDLES = frozenset(
    {
        "i",
        "intent",
        "home",
        "search",
        "share",
        "explore",
        "settings",
        "compose",
        "messages",
        "notifications",
        "hashtag",
        "hashtags",
    }
)
_DEFAULT_TWITTER_FIELD = "Link of Project X ( Formerly Twitter) Profile Page"
_TWITTER_FIELD_ALIASES = (
    "Link of Project X ( Formerly Twitter) Profile Page",
    "Project X ( Formerly Twitter) Profile Page",
    "Project X ( Formly Twitter) Profile Page",
    "Project X ( Formely Twitter) Profile Page",
)
_DEFAULT_COMMANDS = ["pr support"]
_PR_CMD_RE = re.compile(
    r"(?is)^\s*(?:[/@])?pr[\s_-]*support\s*[!.。！]*\s*$"
)
_DEFAULT_LINK_FIELD = "KPI 2 - PR 新闻链接验证"
_DEFAULT_NOTIFY_CHAT = "oc_717a560011483216c49329fda5e43b41"
_PROGRESS_BASE_URL = (
    "https://asgnwd2jk3jn.sg.larksuite.com/base/Kb6rbLenJa4FzWsi6pzlTkdjg0e"
    "?table=tbl5wXOwCptng06w"
)


def is_pr_capture_command(text: str, commands: list[str] | None = None) -> bool:
    raw = (text or "").strip()
    if is_manual_form_command(raw, commands or _DEFAULT_COMMANDS):
        return True
    return bool(_PR_CMD_RE.match(raw))


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip(").,，。]>\"'")


def _host_of(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("mobile."):
        host = host[7:]
    return host


def is_tweet_url(url: str) -> bool:
    try:
        path = (urlparse(url).path or "").lower()
    except ValueError:
        return False
    return _host_of(url) in _TWEET_HOSTS and "/status" in path


def profile_url_from_pr_url(url: str) -> str:
    """https://x.com/handle/status/123 → https://x.com/handle. Empty if not a tweet."""
    if not is_tweet_url(url):
        return ""
    parsed = urlparse(_normalize_url(url))
    parts = [p for p in (parsed.path or "").split("/") if p]
    if len(parts) < 3 or parts[1].lower() != "status":
        return ""
    handle = parts[0].lstrip("@")
    if not handle or handle.lower() in _RESERVED_HANDLES:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
        return ""
    return f"https://x.com/{handle}"


def _twitter_field_name(fields: dict[str, Any]) -> str:
    for key in _TWITTER_FIELD_ALIASES:
        if key in fields:
            return key
    return _DEFAULT_TWITTER_FIELD


def _twitter_already_filled(fields: dict[str, Any]) -> bool:
    from bot.workflow_form_chase import field_is_filled

    return field_is_filled(fields, _DEFAULT_TWITTER_FIELD)


def fill_wallet_twitter_if_empty(
    token: str,
    config: AppConfig,
    *,
    project_name: str,
    profile_url: str,
) -> str:
    """Write profile URL into the wallet Twitter cell only when that cell is empty.

    Returns filled / skipped / unmatched / ambiguous / error / no_url.
    """
    if not profile_url:
        return "no_url"
    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    wallet_table = str(getattr(config, "workflow_wallet_table_id", "") or "").strip()
    name_field = str(
        getattr(config, "workflow_wallet_name_field", "") or "Project name"
    ).strip()
    if not app_token or not wallet_table:
        return "error"
    try:
        rows = list_records(token, app_token, wallet_table)
    except Exception:  # noqa: BLE001
        logger.exception("pr_capture: failed to read wallet table project=%r", project_name)
        return "error"
    key = _normalize_name(project_name)
    matches: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        if not rid:
            continue
        if _normalize_name(_field_text(fields, name_field)) != key:
            continue
        matches.append((rid, fields))
    if not matches:
        logger.info("pr_capture: no wallet row for project=%r", project_name)
        return "unmatched"
    if len(matches) > 1:
        logger.info(
            "pr_capture: ambiguous wallet rows project=%r n=%d — skip Twitter fill",
            project_name,
            len(matches),
        )
        return "ambiguous"
    rid, fields = matches[0]
    if _twitter_already_filled(fields):
        logger.info("pr_capture: wallet Twitter already filled project=%r", project_name)
        return "skipped"
    column = _twitter_field_name(fields)
    try:
        update_record(token, app_token, wallet_table, rid, {column: profile_url})
    except Exception:  # noqa: BLE001
        logger.exception(
            "pr_capture: failed to fill wallet Twitter project=%r record=%s",
            project_name,
            rid,
        )
        return "error"
    logger.info(
        "pr_capture: filled empty wallet Twitter project=%r record=%s url=%s",
        project_name,
        rid,
        profile_url[:80],
    )
    try:
        from bot.workflow_events import append_event

        append_event(
            "wallet_twitter_filled",
            "pr support",
            project_name=project_name,
            text=f"钱包表推特主页为空，已从 PR 链接写入 {profile_url}",
            record_id=rid,
            url=profile_url,
        )
    except Exception:  # noqa: BLE001
        logger.exception("pr_capture: filled Twitter but failed to log event")
    return "filled"


def pick_pr_url(urls: list[str]) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = _normalize_url(raw)
        if not url.lower().startswith("http"):
            continue
        if url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    for url in cleaned:
        if is_tweet_url(url):
            return url
    return cleaned[0] if cleaned else ""


def collect_urls_from_text(text: str) -> list[str]:
    return [_normalize_url(m.group(0)) for m in _URL_RE.finditer(text or "")]


def collect_urls_from_message(message: Any) -> list[str]:
    urls: list[str] = []
    text = getattr(message, "raw_text", None) or getattr(message, "message", None) or ""
    urls.extend(collect_urls_from_text(str(text)))
    for ent in getattr(message, "entities", None) or []:
        extra = getattr(ent, "url", None)
        if extra:
            urls.append(str(extra))
    preview = getattr(message, "web_preview", None)
    if preview is not None and getattr(preview, "url", None):
        urls.append(str(preview.url))
    media = getattr(message, "media", None)
    webpage = getattr(media, "webpage", None) if media is not None else None
    if webpage is not None and getattr(webpage, "url", None):
        urls.append(str(webpage.url))
    return urls


def tg_message_link(chat_id: int, msg_id: int) -> str:
    raw = str(int(chat_id))
    if raw.startswith("-100"):
        return f"https://t.me/c/{raw[4:]}/{int(msg_id)}"
    return f"https://t.me/c/{abs(int(chat_id))}/{int(msg_id)}"


def _collect_matches(
    config: AppConfig,
    records: list[dict[str, Any]],
    chat_id: int,
    chat_title: str,
) -> list[tuple[str, str, dict[str, Any]]]:
    """Prefer exact TG chat id field matches; else fuzzy title matches."""
    id_matches: list[tuple[str, str, dict[str, Any]]] = []
    field = str(getattr(config, "workflow_tg_chat_id_field", "") or "").strip()
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


def build_pr_notify_text(
    *,
    project_name: str,
    chat_title: str,
    url: str,
    operator: str = "",
    record_id: str = "",
) -> str:
    lines = [
        "[KPI-PR captured]",
        f"Project: {project_name or 'unknown project'}",
        f"TG group: {chat_title or 'unknown group'}",
        f"Link: {url}",
    ]
    if operator:
        lines.append(f"By: {operator}")
    if record_id:
        lines.append(f"Tracker: {_PROGRESS_BASE_URL}&record={record_id}")
    return "\n".join(lines)


def _notify_chat_id(config: AppConfig) -> str:
    return str(
        getattr(config, "pr_capture_notify_chat_id", "")
        or getattr(config, "workflow_verify_alert_lark_chat_id", "")
        or _DEFAULT_NOTIFY_CHAT
    ).strip()


async def capture_pr_tweet(
    client: TelegramClient,
    config: AppConfig,
    command_message: Message,
    chat_id: int,
    chat_title: str,
) -> str:
    del client  # signature matches other workflow handlers
    if not getattr(config, "pr_capture_enabled", False):
        return "PR capture is disabled."

    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    table_id = str(getattr(config, "workflow_progress_table_id", "") or "").strip()
    link_field = str(
        getattr(config, "pr_capture_link_field", "") or _DEFAULT_LINK_FIELD
    ).strip()
    if not app_token or not table_id or not link_field:
        return "PR capture is not configured."

    quoted = await command_message.get_reply_message()
    if quoted is None:
        return "Quote the PR post in this group, then reply `pr support`."

    url = pick_pr_url(collect_urls_from_message(quoted))
    if not url:
        return (
            "Quoted message has no link. Quote the post that contains "
            "the URL, then reply `pr support`."
        )

    sender = await command_message.get_sender()
    operator = ""
    if sender is not None:
        username = getattr(sender, "username", None)
        operator = f"@{username}" if username else str(getattr(sender, "id", "") or "")

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return "Missing LARK_APP_ID / LARK_APP_SECRET in .env"

    loop = asyncio.get_running_loop()
    try:
        token = await loop.run_in_executor(
            None, get_tenant_access_token, app_id, app_secret
        )
        records = await loop.run_in_executor(
            None,
            list_records,
            token,
            app_token,
            table_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pr_capture: failed to read Lark chat=%s", chat_id)
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
            "Not writing the PR link until the group maps to one project."
        )

    record_id, project_name, _fields = matches[0]
    try:
        await loop.run_in_executor(
            None,
            update_record,
            token,
            app_token,
            table_id,
            record_id,
            {link_field: url},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "pr_capture: failed to update KPI 2 project=%r record=%s",
            project_name,
            record_id,
        )
        return f"Matched {project_name!r} but failed to write the PR link: {exc}"

    live_link_field = str(
        getattr(config, "workflow_live_link_field", "") or "已上线链接🔗"
    )
    try:
        log_capture_event(
            config,
            record_id=record_id,
            project=project_name,
            url=url,
            site=link_str(_fields.get(live_link_field)) or _field_text(_fields, live_link_field),
        )
    except Exception:  # noqa: BLE001
        logger.exception("pr_capture: saved KPI 2 but failed to log weekly event")

    logger.info(
        "PR KPI 2 overwritten chat=%s project=%r record=%s url=%s",
        chat_id,
        project_name,
        record_id,
        url[:120],
    )
    lines = [
        "Saved PR link.",
        f"Project: {project_name}",
        url,
    ]
    profile_url = profile_url_from_pr_url(url)
    if profile_url:
        try:
            twitter_result = await loop.run_in_executor(
                None,
                lambda: fill_wallet_twitter_if_empty(
                    token,
                    config,
                    project_name=project_name,
                    profile_url=profile_url,
                ),
            )
        except Exception:  # noqa: BLE001
            logger.exception("pr_capture: wallet Twitter fill crashed project=%r", project_name)
            twitter_result = "error"
        if twitter_result == "filled":
            lines.append("Twitter profile Filled")
    notify_on = bool(getattr(config, "pr_capture_notify_enabled", True))
    lark_chat = _notify_chat_id(config) if notify_on else ""
    if notify_on and lark_chat:
        msg = build_pr_notify_text(
            project_name=project_name,
            chat_title=chat_title,
            url=url,
            operator=operator,
            record_id=record_id,
        )
        try:
            await loop.run_in_executor(None, send_text_to_chat, token, lark_chat, msg)
            lines.append("Notified Botchain social media team.")
        except Exception:  # noqa: BLE001
            logger.exception("pr_capture: PR link saved but Lark notify failed")
            lines.append("Saved the PR link, but failed to notify Botchain social media team. Check logs.")
    elif notify_on:
        lines.append("Saved the PR link; Lark notify skipped (no chat id).")
    return "\n".join(lines)
