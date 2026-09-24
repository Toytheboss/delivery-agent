"""Mainnet-live: check Roy/Josh TG membership, send form, ping Project verification push."""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from bot.lark_bitable import get_tenant_access_token
from bot.lark_im import send_text_to_chat
from bot.workflow_form_dispatch import (
    _chat_ids_already_sent_form,
    _field_text,
    _load_state,
    _mark_sent_in_lark,
    _parse_chat_id,
    _save_state,
    build_folder_title_map,
    match_project_to_chat,
    send_form_messages,
)

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
_SKIP_NOTIFY_SOURCES = frozenset({"startup_catchup"})


def parse_bd_person(fields: dict[str, Any], field_name: str) -> tuple[str, str]:
    """Return (open_id, display_name) from a Lark user field."""
    value = fields.get(field_name)
    if isinstance(value, list) and value:
        item = value[0]
        if isinstance(item, dict):
            oid = str(item.get("id") or item.get("open_id") or "").strip()
            name = str(item.get("name") or item.get("text") or "").strip()
            return oid, name
    if isinstance(value, dict):
        oid = str(value.get("id") or value.get("open_id") or "").strip()
        name = str(value.get("name") or value.get("text") or "").strip()
        return oid, name
    return "", str(value or "").strip()


def classify_case(roy_in: bool, josh_in: bool) -> int:
    if roy_in and josh_in:
        return 1
    if roy_in and not josh_in:
        return 2
    if josh_in and not roy_in:
        return 3
    return 4


def build_onboard_message(
    *,
    case: int,
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
    group_label = (group or project).strip() or project
    if case == 1:
        body = (
            f"**{project}** is live on mainnet. Delivery (Roy and Josh) have joined "
            f"the TG group. The Onboarding Google Form has been sent to "
            f"**{group_label}**. Please:\n\n"
            "1. Help the project submit the required info (Twitter, contract address, "
            "etc.) to the Onboarding Google Form as soon as possible\n"
            "2. Share the mainnet-live PR tweet in the TG group and @ Roy and Josh"
        )
    elif case == 2:
        body = (
            f"**{project}** is live on mainnet. Delivery: Roy has joined the TG group; "
            f"Josh has not been added yet. The Onboarding Google Form has been sent to "
            f"**{group_label}**. Please:\n\n"
            "1. Add Josh to the TG group\n"
            "2. Help the project submit the required info (Twitter, contract address, "
            "etc.) to the Onboarding Google Form as soon as possible\n"
            "3. Share the mainnet-live PR tweet in the TG group and @ Roy and Josh"
        )
    elif case == 3:
        body = (
            f"**{project}** is live on mainnet. Delivery: Josh has joined the TG group; "
            f"Roy has not been added yet. The Onboarding Google Form has been sent to "
            f"**{group_label}**. Please:\n\n"
            "1. Add Roy to the TG group\n"
            "2. Help the project submit the required info (Twitter, contract address, "
            "etc.) to the Onboarding Google Form as soon as possible\n"
            "3. Share the mainnet-live PR tweet in the TG group and @ Roy and Josh"
        )
    else:
        body = (
            f"**{project}** is live on mainnet. Roy / Josh were not detected in a TG "
            "group. The Onboarding Google Form was not sent. Please:\n\n"
            "1. Create the project TG group, add Roy and Josh, then trigger the form send\n"
            "2. Help the project submit the required info (Twitter, contract address, "
            "etc.) to the Onboarding Google Form as soon as possible\n"
            "3. Share the mainnet-live PR tweet in the TG group and @ Roy and Josh"
        )
    return f"{at}\n\n{body}"


def account_key(config: Any) -> str:
    raw = str(getattr(config, "workflow_live_onboard_account", "") or "").strip().lower()
    if raw in {"roy", "josh"}:
        return raw
    return "roy" if bool(getattr(config, "group_replies_enabled", False)) else "josh"


def _state_path(config: Any) -> Path:
    override = str(getattr(config, "workflow_live_onboard_state_file", "") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else ROOT / path
    shared = Path("/opt/botchain-shared/live_onboard_state.json")
    if shared.parent.is_dir():
        return shared
    return ROOT / "data" / "live_onboard_state.json"


@contextmanager
def _locked_state(path: Path) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        projects = data.get("projects")
        if not isinstance(projects, dict):
            data["projects"] = {}
        yield data
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        handle.flush()


def _project_entry(data: dict[str, Any], rid: str) -> dict[str, Any]:
    projects = data.setdefault("projects", {})
    entry = projects.get(rid)
    if not isinstance(entry, dict):
        entry = {}
        projects[rid] = entry
    return entry


async def account_in_chat(client: TelegramClient, chat_id: int) -> tuple[bool, str]:
    """True when this Telegram account can access the live group (not a leftover id)."""
    from bot.folder_auto_add import _is_stale_upgraded_chat

    try:
        entity = await client.get_entity(chat_id)
    except Exception:  # noqa: BLE001
        return False, ""
    if _is_stale_upgraded_chat(entity):
        migrated = getattr(entity, "migrated_to", None)
        if migrated is None:
            return False, ""
        try:
            entity = await client.get_entity(migrated)
        except Exception:  # noqa: BLE001
            return False, ""
    title = str(getattr(entity, "title", None) or "").strip()
    try:
        await client.get_permissions(entity)
    except Exception:  # noqa: BLE001
        return False, title
    return True, title


async def _dialog_title_map(client: TelegramClient, config: Any) -> dict[int, str]:
    from telethon import utils

    from bot.folder_auto_add import _is_group_or_channel, _is_stale_upgraded_chat
    from bot.group_welcome import title_matches_project
    from bot.tg_rate_limit import tg_heavy_section

    keywords = (
        list(getattr(config, "folder_auto_add_keywords", None) or [])
        or list(getattr(config, "welcome_name_keywords", None) or [])
    )
    out: dict[int, str] = {}
    async with tg_heavy_section():
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not _is_group_or_channel(entity) or _is_stale_upgraded_chat(entity):
                continue
            title = str(getattr(entity, "title", None) or "").strip()
            if keywords and not title_matches_project(title, keywords):
                continue
            try:
                out[int(utils.get_peer_id(entity))] = title
            except Exception:  # noqa: BLE001
                continue
    return out


async def resolve_project_chat(
    client: TelegramClient,
    config: Any,
    scope: FolderScope | None,
    *,
    name: str,
    fields: dict[str, Any],
    preferred_chat_id: int | None,
    preferred_chat_title: str | None,
) -> tuple[int | None, str, str]:
    """Return (chat_id, title, reason). Prefers Lark TG id, then live dialogs."""
    chat_id: int | None = None
    reason = ""
    field = str(getattr(config, "workflow_tg_chat_id_field", "") or "").strip()
    if field:
        chat_id = _parse_chat_id(_field_text(fields, field))
        if chat_id is not None:
            reason = "lark TG群ID field"

    titles: dict[int, str] = {}
    if preferred_chat_id is not None:
        titles[preferred_chat_id] = (
            (preferred_chat_title or "").strip() or name
        )
        if chat_id is None:
            matched, why = match_project_to_chat(name, titles)
            if matched == preferred_chat_id:
                chat_id = preferred_chat_id
                reason = f"preferred chat ({why})"

    if chat_id is None:
        if scope is not None:
            if not scope.chat_ids:
                await scope.refresh()
            titles.update(await build_folder_title_map(client, scope.chat_ids))
        try:
            titles.update(await _dialog_title_map(client, config))
        except Exception:
            logger.exception("live-onboard: dialog title scan failed")
        chat_id, reason = match_project_to_chat(name, titles)

    title = ""
    if chat_id is not None:
        title = titles.get(chat_id) or (preferred_chat_title or "").strip()
        if not title:
            _in, resolved = await account_in_chat(client, chat_id)
            if resolved:
                title = resolved
    return chat_id, title, reason or "unmatched"


async def _send_form_if_needed(
    client: TelegramClient,
    config: Any,
    *,
    token: str,
    rid: str,
    name: str,
    chat_id: int,
    chat_title: str,
    source: str,
) -> str:
    root = ROOT
    state_path = root / config.workflow_state_file
    sent = _load_state(state_path)
    if rid in sent:
        return "already_sent"
    if chat_id in _chat_ids_already_sent_form(config):
        sent.add(rid)
        _save_state(state_path, sent)
        return "already_sent_chat"
    try:
        await send_form_messages(client, config, chat_id, name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("live-onboard form send failed for %r", name)
        return f"send_failed:{exc}"
    sent.add(rid)
    _save_state(state_path, sent)
    try:
        loop = asyncio.get_running_loop()
        await _mark_sent_in_lark(loop, token, config, rid)
    except Exception:  # noqa: BLE001
        logger.exception("live-onboard mark form-sent in Lark failed for %r", name)
    try:
        from bot.workflow_form_chase import note_form_sent

        note_form_sent(
            config,
            record_id=rid,
            project_name=name,
            chat_id=chat_id,
            source=source or "live_onboard",
        )
    except Exception:  # noqa: BLE001
        logger.exception("form-chase note failed for %r", name)
    logger.info(
        "live-onboard form sent %r (%s) -> %s (%s)",
        name,
        rid,
        chat_id,
        chat_title,
    )
    return "sent"


def _form_ok(status: str) -> bool:
    return status in {"sent", "already_sent", "already_sent_chat"}


async def _notify_lark(config: Any, entry: dict[str, Any], fields: dict[str, Any]) -> str:
    chat_id = str(getattr(config, "workflow_live_onboard_lark_chat_id", "") or "").strip()
    if not chat_id:
        logger.warning("live-onboard: lark chat_id empty; skip notify")
        return "skipped_no_chat"
    bd_field = str(getattr(config, "workflow_live_onboard_bd_field", "") or "BD")
    bd_open_id, bd_name = parse_bd_person(fields, bd_field)
    case = int(entry.get("case") or 4)
    text = build_onboard_message(
        case=case,
        project=str(entry.get("project_name") or ""),
        group=str(entry.get("chat_title") or ""),
        bd_name=bd_name,
        bd_open_id=bd_open_id,
    )
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return "skipped_no_lark_creds"
    token = get_tenant_access_token(app_id, app_secret)
    send_text_to_chat(token, chat_id, text)
    logger.info(
        "live-onboard notified case=%s project=%r bd=%s",
        case,
        entry.get("project_name"),
        bd_name,
    )
    return "sent"


async def _finalize_notify(
    config: Any,
    *,
    rid: str,
    fields: dict[str, Any],
    source: str,
) -> None:
    wait_s = max(int(getattr(config, "workflow_live_onboard_peer_wait_seconds", 90) or 0), 0)
    if wait_s:
        await asyncio.sleep(wait_s)
    if source in _SKIP_NOTIFY_SOURCES:
        return
    path = _state_path(config)
    with _locked_state(path) as data:
        entry = _project_entry(data, rid)
        if entry.get("notify") == "sent":
            return
        roy_in = bool(entry.get("roy_in"))
        josh_in = bool(entry.get("josh_in"))
        form_status = str(entry.get("form") or "")
        case = classify_case(roy_in, josh_in)
        if not _form_ok(form_status):
            case = 4
        entry["case"] = case
        entry["notify"] = "sending"
        snapshot = dict(entry)
    try:
        notify = await _notify_lark(config, snapshot, fields)
    except Exception:
        logger.exception("live-onboard Lark notify failed for %s", rid)
        notify = "failed"
        with _locked_state(path) as data:
            entry = _project_entry(data, rid)
            if entry.get("notify") != "sent":
                entry["notify"] = notify
        return
    with _locked_state(path) as data:
        entry = _project_entry(data, rid)
        if notify == "sent":
            entry["notify"] = "sent"
            entry["notified_at"] = time.time()
        elif entry.get("notify") != "sent":
            entry["notify"] = notify


async def run_live_onboard(
    client: TelegramClient,
    config: Any,
    scope: FolderScope | None,
    *,
    token: str,
    rid: str,
    name: str,
    fields: dict[str, Any],
    source: str,
    preferred_chat_id: int | None = None,
    preferred_chat_title: str | None = None,
) -> dict[str, Any]:
    """Check membership, send form if this account is in the group, schedule Lark ping."""
    out: dict[str, Any] = {"form": "skipped", "case": None, "chat_id": None, "chat_title": ""}
    if not getattr(config, "workflow_live_onboard_enabled", False):
        return out
    if not getattr(config, "workflow_google_form_url", ""):
        out["form"] = "no_form_url"
        return out

    chat_id, chat_title, reason = await resolve_project_chat(
        client,
        config,
        scope,
        name=name,
        fields=fields,
        preferred_chat_id=preferred_chat_id,
        preferred_chat_title=preferred_chat_title,
    )
    in_group = False
    if chat_id is not None:
        in_group, live_title = await account_in_chat(client, chat_id)
        if live_title:
            chat_title = live_title
    key = account_key(config)
    form_status = "no_group" if chat_id is None else "not_in_group"
    if chat_id is None:
        logger.warning("live-onboard no group for %r (%s): %s", name, rid, reason)
    elif in_group:
        form_status = await _send_form_if_needed(
            client,
            config,
            token=token,
            rid=rid,
            name=name,
            chat_id=chat_id,
            chat_title=chat_title,
            source=source,
        )
    else:
        logger.info(
            "live-onboard %s not in chat_id=%s for %r (%s)",
            key,
            chat_id,
            name,
            rid,
        )

    now = time.time()
    path = _state_path(config)
    should_notify = False
    with _locked_state(path) as data:
        entry = _project_entry(data, rid)
        entry["project_name"] = name
        if chat_id is not None:
            entry["chat_id"] = chat_id
        if chat_title:
            entry["chat_title"] = chat_title
        entry[f"{key}_in"] = bool(in_group)
        entry[f"{key}_checked_at"] = now
        if _form_ok(form_status):
            entry["form"] = form_status
            entry["form_by"] = key
        elif not _form_ok(str(entry.get("form") or "")):
            entry["form"] = form_status
        roy_in = bool(entry.get("roy_in"))
        josh_in = bool(entry.get("josh_in"))
        case = classify_case(roy_in, josh_in)
        if not _form_ok(str(entry.get("form") or "")):
            case = 4
        entry["case"] = case
        if (
            source not in _SKIP_NOTIFY_SOURCES
            and entry.get("notify") not in {"sent", "scheduled"}
        ):
            entry["notify"] = "scheduled"
            should_notify = True
        out["case"] = case
        out["form"] = str(entry.get("form") or form_status)
        out["chat_id"] = entry.get("chat_id")
        out["chat_title"] = str(entry.get("chat_title") or "")

    if should_notify:
        asyncio.create_task(
            _finalize_notify(config, rid=rid, fields=fields, source=source),
            name=f"live-onboard-notify-{rid}",
        )
    return out


async def maybe_onboard_on_join(
    client: TelegramClient,
    config: Any,
    scope: FolderScope | None,
    *,
    chat_id: int,
    chat_title: str,
) -> None:
    """If this group maps to a live row whose form is still missing, run onboard."""
    if not getattr(config, "workflow_enabled", False):
        return
    if not getattr(config, "workflow_live_onboard_enabled", False):
        return
    from bot.group_welcome import title_matches_project
    from bot.workflow_form_dispatch import _field_text
    from bot.workflow_live_trigger import _load_progress_records, process_live_project

    keywords = (
        list(getattr(config, "folder_auto_add_keywords", None) or [])
        or list(getattr(config, "welcome_name_keywords", None) or [])
    )
    if keywords and not title_matches_project(chat_title, keywords):
        return
    try:
        _token, records = await _load_progress_records(config)
    except Exception:
        logger.exception("live-onboard join: failed to load Lark records")
        return
    live = str(getattr(config, "workflow_trigger_status", "") or "")
    name_field = str(getattr(config, "workflow_project_name_field", "") or "")
    titles = {chat_id: chat_title}
    for record in records:
        rid = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        if not rid:
            continue
        if _field_text(fields, config.workflow_status_field) != live:
            continue
        project = _field_text(fields, name_field)
        if not project:
            continue
        matched, _reason = match_project_to_chat(project, titles)
        if matched != chat_id:
            continue
        path = _state_path(config)
        with _locked_state(path) as data:
            entry = _project_entry(data, rid)
            form_status = str(entry.get("form") or "")
            notify_status = str(entry.get("notify") or "")
            prev_case = int(entry.get("case") or 0)
            already_ok = _form_ok(form_status) and notify_status == "sent" and prev_case != 4
        if already_ok:
            continue
        if notify_status == "sent" and prev_case == 4:
            with _locked_state(path) as data:
                entry = _project_entry(data, rid)
                entry["notify"] = ""
        logger.info(
            "live-onboard join catch-up project=%r chat_id=%s title=%r",
            project,
            chat_id,
            chat_title,
        )
        await process_live_project(
            client,
            config,
            scope,  # type: ignore[arg-type]
            record_id=rid,
            project_name=project,
            require_live_status=True,
            source="join_catchup",
            preferred_chat_id=chat_id,
            preferred_chat_title=chat_title,
        )
        return


def register_live_onboard_join_handler(
    client: TelegramClient,
    config: Any,
    my_id: int | None,
    *,
    scope: FolderScope | None = None,
) -> None:
    from telethon import events, utils

    @client.on(events.ChatAction)
    async def _on_chat_action(event: events.ChatAction.Event) -> None:
        if not getattr(config, "workflow_live_onboard_enabled", False):
            return
        added_me = False
        if event.user_added or event.created:
            user_ids = list(event.user_ids or [])
            if event.user_id:
                user_ids.append(event.user_id)
            if my_id is not None and my_id in user_ids:
                added_me = True
        if getattr(event, "user_joined", False) and event.user_id == my_id:
            added_me = True
        if not added_me:
            return
        try:
            chat = await event.get_chat()
        except Exception:  # noqa: BLE001
            logger.exception("live-onboard join: get_chat failed")
            return
        title = str(getattr(chat, "title", None) or "").strip()
        try:
            cid = int(utils.get_peer_id(chat))
        except Exception:  # noqa: BLE001
            cid = int(event.chat_id or 0)
        if not cid:
            return
        await asyncio.sleep(1.0)
        try:
            await maybe_onboard_on_join(
                client, config, scope, chat_id=cid, chat_title=title
            )
        except Exception:
            logger.exception("live-onboard join catch-up failed chat_id=%s", cid)
