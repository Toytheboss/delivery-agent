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
from bot.lark_im import send_markdown_post_to_chat
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
_SKIP_NOTIFY_SOURCES = frozenset({"startup_catchup", "join_catchup"})
_RETRY_NOTIFY = frozenset({"need_roy", "scheduled", "sending"})


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
    form_sent: bool,
) -> str:
    at = (
        f'<at user_id="{bd_open_id}">{bd_name or "BD"}</at>'
        if bd_open_id
        else f"@{bd_name or 'BD'}"
    )
    project_label = (project or "Unknown project").strip() or "Unknown project"
    has_group = bool((group or "").strip())
    group_label = (group or "").strip() or "not matched"
    form_please = (
        "Help the project submit Twitter and the contract address to the form"
    )
    pr_please = (
        "Share the mainnet-live PR tweet in the TG group and @ Roy and Josh"
    )
    roy_in = case in {1, 2}
    josh_in = case in {1, 3}
    if case == 1:
        delivery = "Roy and Josh have joined"
    elif case == 2:
        delivery = "Roy has joined; Josh has not been added"
    elif case == 3:
        delivery = "Josh has joined; Roy has not been added"
    elif has_group:
        delivery = "Roy / Josh were not detected in this TG group"
    else:
        delivery = "Roy / Josh were not detected in a TG group"
    form = (
        "Onboarding Google Form has been sent"
        if form_sent
        else "Onboarding Google Form was not sent"
    )
    please: list[str] = []
    if not has_group:
        please.append(
            "Create the project TG group, add Roy and Josh, then trigger the form send"
        )
    else:
        missing = []
        if not roy_in:
            missing.append("Roy")
        if not josh_in:
            missing.append("Josh")
        if missing:
            please.append(f"Add {' and '.join(missing)} to the TG group")
        if not form_sent:
            please.append("Trigger the Onboarding Google Form send")
    please.append(form_please)
    please.append(pr_please)
    numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(please, start=1))
    return (
        f"{at}\n\n"
        f"**Project:** `{project_label}`\n"
        f"**Status:** Live on mainnet\n"
        f"**TG group:** `{group_label}`\n"
        f"**Delivery:** {delivery}\n"
        f"**Form:** {form}\n\n"
        f"**Please:**\n"
        f"{numbered}"
    )


def account_key(config: Any) -> str:
    raw = str(getattr(config, "workflow_live_onboard_account", "") or "").strip().lower()
    if raw in {"roy", "josh"}:
        return raw
    return "roy" if bool(getattr(config, "group_replies_enabled", False)) else "josh"


def sends_lark_notify(config: Any) -> bool:
    """Only Roy号 / roy's lark agent #1 posts to Project verification push."""
    return account_key(config) == "roy"


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


_DATA_ROOTS = (
    Path("/opt/botchain-qa-tg-bot/data"),
    Path("/opt/delivery-agent/data"),
    ROOT / "data",
)


def _unique_data_roots() -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for root in _DATA_ROOTS:
        try:
            if not root.is_dir():
                continue
            key = str(root.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _parse_title_cache_file(path: Path) -> dict[int, str]:
    raw = _read_json_dict(path)
    payload = raw.get("titles") if isinstance(raw.get("titles"), dict) else raw
    if not isinstance(payload, dict):
        return {}
    titles: dict[int, str] = {}
    for key, value in payload.items():
        try:
            chat_id = int(key)
        except (TypeError, ValueError):
            continue
        title = value.get("title") if isinstance(value, dict) else value
        title = str(title or "").strip()
        if title:
            titles[chat_id] = title
    return titles


def load_peer_folder_titles() -> tuple[dict[int, str], set[int], set[int]]:
    """Union Folder title caches. Chat ids are tagged by which account cached them."""
    titles: dict[int, str] = {}
    roy_ids: set[int] = set()
    josh_ids: set[int] = set()
    for root in _unique_data_roots():
        path = root / "folder_title_cache.json"
        if not path.is_file():
            continue
        parsed = _parse_title_cache_file(path)
        path_s = str(path).lower()
        is_roy = "botchain-qa" in path_s
        is_josh = "delivery-agent" in path_s or "josh-dashboard" in path_s
        for chat_id, title in parsed.items():
            titles[chat_id] = title
            if is_roy:
                roy_ids.add(chat_id)
            if is_josh:
                josh_ids.add(chat_id)
    return titles, roy_ids, josh_ids


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _config_state_paths(config: Any, attr: str, default: str) -> list[Path]:
    rel = str(getattr(config, attr, "") or default)
    names = {Path(rel).name, Path(default).name}
    paths: list[Path] = []
    seen: set[str] = set()
    local = Path(rel)
    if not local.is_absolute():
        local = ROOT / local
    candidates = [local]
    for root in _unique_data_roots():
        for name in names:
            candidates.append(root / name)
    for path in candidates:
        try:
            key = str(path.resolve()) if path.exists() else str(path)
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def form_already_sent(
    config: Any,
    *,
    rid: str,
    chat_id: int | None,
) -> bool:
    """True if either account already sent the onboarding form."""
    rid = str(rid or "").strip()
    for path in _config_state_paths(
        config, "workflow_state_file", "data/form_dispatch_state.json"
    ):
        sent = {
            str(item)
            for item in (_read_json_dict(path).get("sent_record_ids") or [])
        }
        if rid and rid in sent:
            return True
    for path in _config_state_paths(
        config, "workflow_form_chase_state_file", "data/form_chase_state.json"
    ):
        projects = _read_json_dict(path).get("projects") or {}
        if not isinstance(projects, dict):
            continue
        if rid:
            meta = projects.get(rid)
            if isinstance(meta, dict) and (
                meta.get("first_sent_at") or meta.get("last_sent_at")
            ):
                return True
        if chat_id is None:
            continue
        for meta in projects.values():
            if not isinstance(meta, dict):
                continue
            try:
                if int(meta.get("chat_id")) != int(chat_id):
                    continue
            except (TypeError, ValueError):
                continue
            if meta.get("first_sent_at") or meta.get("last_sent_at"):
                return True
    if chat_id is not None and int(chat_id) in _chat_ids_already_sent_form(config):
        return True
    return False


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
        titles.update(load_peer_folder_titles()[0])
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


def _mark_onboard_form_sent(
    config: Any,
    rid: str,
    *,
    by: str,
    chat_id: int,
    chat_title: str,
    project_name: str,
) -> None:
    path = _state_path(config)
    with _locked_state(path) as data:
        entry = _project_entry(data, rid)
        entry["project_name"] = project_name or entry.get("project_name") or ""
        if chat_id:
            entry["chat_id"] = int(chat_id)
        if chat_title:
            entry["chat_title"] = chat_title
        entry["form"] = "sent"
        entry["form_by"] = by


def remember_group_membership(
    config: Any,
    *,
    rid: str,
    project_name: str,
    chat_id: int,
    chat_title: str,
    roy_in: bool,
    josh_in: bool,
) -> None:
    """Record who was in the group at Mark live, before the Lark ping is composed."""
    path = _state_path(config)
    with _locked_state(path) as data:
        entry = _project_entry(data, rid)
        entry["project_name"] = project_name or entry.get("project_name") or ""
        entry["chat_id"] = int(chat_id)
        if chat_title:
            entry["chat_title"] = chat_title
        entry["roy_in"] = bool(roy_in)
        entry["josh_in"] = bool(josh_in)


async def lookup_peer_in_chat(
    client: TelegramClient, chat_id: int, peer: str
) -> bool | None:
    """True/False when Telegram answered; None when the lookup itself failed."""
    username = {"roy": "Roy4by4", "josh": "Josh_0zh"}.get(str(peer or "").strip().lower(), "")
    if not username:
        return None
    try:
        user = await client.get_entity(username)
        entity = await client.get_entity(chat_id)
    except Exception:
        logger.exception(
            "live-onboard: cannot resolve peer=%s chat=%s", peer, chat_id
        )
        return None
    try:
        uid = int(getattr(user, "id", 0) or 0)
    except (TypeError, ValueError):
        uid = 0
    if not uid:
        return None
    from telethon.tl.types import Channel, Chat

    if isinstance(entity, Channel):
        from telethon.errors import UserNotParticipantError
        from telethon.tl.functions.channels import GetParticipantRequest

        try:
            await client(GetParticipantRequest(entity, user))
            return True
        except UserNotParticipantError:
            return False
        except Exception:
            logger.exception(
                "live-onboard: channel participant lookup failed peer=%s chat=%s",
                peer,
                chat_id,
            )
            return None
    if isinstance(entity, Chat):
        from telethon.tl.functions.messages import GetFullChatRequest

        try:
            full = await client(GetFullChatRequest(entity.id))
        except Exception:
            logger.exception(
                "live-onboard: basic-group lookup failed peer=%s chat=%s",
                peer,
                chat_id,
            )
            return None
        parts = getattr(getattr(full, "full_chat", None), "participants", None)
        users = getattr(parts, "participants", None) or []
        return any(int(getattr(item, "user_id", 0) or 0) == uid for item in users)
    return None


async def peer_account_in_chat(client: TelegramClient, chat_id: int, peer: str) -> bool:
    """True when the other bot account is a member of this group."""
    found = await lookup_peer_in_chat(client, chat_id, peer)
    return bool(found)


def merge_membership(
    *,
    self_key: str,
    self_in: bool,
    stored_roy: bool,
    stored_josh: bool,
    peer_live: bool | None,
) -> tuple[bool, bool]:
    """OR this account's live check with stored flags; apply peer live only if it answered."""
    roy_in = bool(stored_roy)
    josh_in = bool(stored_josh)
    if self_key == "roy":
        roy_in = roy_in or bool(self_in)
        if peer_live is True:
            josh_in = True
        elif peer_live is False:
            josh_in = False
    else:
        josh_in = josh_in or bool(self_in)
        if peer_live is True:
            roy_in = True
        elif peer_live is False:
            roy_in = False
    return roy_in, josh_in


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
    from bot.workflow_form_claim import (
        begin_form_send,
        claim_path_for,
        finish_form_send,
        release_form_send,
    )

    owner = account_key(config)
    claim_path = claim_path_for(config)
    root = ROOT
    state_path = root / config.workflow_state_file
    sent = _load_state(state_path)
    if form_already_sent(config, rid=rid, chat_id=chat_id) or rid in sent:
        sent.add(rid)
        _save_state(state_path, sent)
        _mark_onboard_form_sent(
            config,
            rid,
            by=owner,
            chat_id=chat_id,
            chat_title=chat_title,
            project_name=name,
        )
        finish_form_send(claim_path, rid, owner)
        return "already_sent"
    if chat_id in _chat_ids_already_sent_form(config):
        sent.add(rid)
        _save_state(state_path, sent)
        finish_form_send(claim_path, rid, owner)
        return "already_sent_chat"
    decision = begin_form_send(
        claim_path,
        rid,
        owner,
        chat_id=chat_id,
        project_name=name,
        chat_title=chat_title,
    )
    if decision == "done":
        sent.add(rid)
        _save_state(state_path, sent)
        return "already_sent"
    if decision != "send":
        logger.info(
            "live-onboard form deferred %r (%s) caller=%s claim=%s",
            name,
            rid,
            owner,
            decision,
        )
        return "deferred"
    try:
        await send_form_messages(client, config, chat_id, name)
    except Exception as exc:  # noqa: BLE001
        release_form_send(claim_path, rid, owner)
        logger.exception("live-onboard form send failed for %r", name)
        return f"send_failed:{exc}"
    finish_form_send(claim_path, rid, owner)
    sent.add(rid)
    _save_state(state_path, sent)
    _mark_onboard_form_sent(
        config,
        rid,
        by=owner,
        chat_id=chat_id,
        chat_title=chat_title,
        project_name=name,
    )
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
        "live-onboard form sent %r (%s) -> %s (%s) by %s",
        name,
        rid,
        chat_id,
        chat_title,
        owner,
    )
    return "sent"


def _form_ok(status: str) -> bool:
    return status in {"sent", "already_sent", "already_sent_chat"}


async def _notify_lark(config: Any, entry: dict[str, Any], fields: dict[str, Any]) -> str:
    if not sends_lark_notify(config):
        return "skipped_not_roy"
    chat_id = str(getattr(config, "workflow_live_onboard_lark_chat_id", "") or "").strip()
    if not chat_id:
        logger.warning("live-onboard: lark chat_id empty; skip notify")
        return "skipped_no_chat"
    bd_field = str(getattr(config, "workflow_live_onboard_bd_field", "") or "BD")
    bd_open_id, bd_name = parse_bd_person(fields, bd_field)
    case = int(entry.get("case") or 4)
    form_sent = bool(entry.get("form_sent")) or _form_ok(str(entry.get("form") or ""))
    text = build_onboard_message(
        case=case,
        project=str(entry.get("project_name") or ""),
        group=str(entry.get("chat_title") or ""),
        bd_name=bd_name,
        bd_open_id=bd_open_id,
        form_sent=form_sent,
    )
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return "skipped_no_lark_creds"
    token = get_tenant_access_token(app_id, app_secret)
    send_markdown_post_to_chat(token, chat_id, text)
    logger.info(
        "live-onboard notified case=%s project=%r bd=%s",
        case,
        entry.get("project_name"),
        bd_name,
    )
    try:
        from bot.workflow_events import log_delivery

        log_delivery(
            "verification_push_onboard",
            "Project verification push",
            project_name=str(entry.get("project_name") or ""),
            record_id=str(entry.get("record_id") or ""),
            text=(
                f"{entry.get('project_name') or '项目'} 已推送上线核对到 "
                f"Project verification push（case {case}）"
            ),
            case=case,
            lark_chat_id=chat_id,
        )
    except Exception:
        pass
    return "sent"


async def _finalize_notify(
    config: Any,
    *,
    rid: str,
    fields: dict[str, Any],
    source: str,
    client: TelegramClient | None = None,
) -> None:
    if not sends_lark_notify(config):
        path = _state_path(config)
        with _locked_state(path) as data:
            entry = _project_entry(data, rid)
            if entry.get("notify") != "sent":
                entry["notify"] = "need_roy"
        return
    if source in _SKIP_NOTIFY_SOURCES:
        return
    path = _state_path(config)
    with _locked_state(path) as data:
        entry = _project_entry(data, rid)
        if entry.get("notify") == "sent":
            return
        if entry.get("notify") == "sending":
            return
        chat_id_raw = entry.get("chat_id")
        try:
            chat_id = int(chat_id_raw) if chat_id_raw not in (None, "") else None
        except (TypeError, ValueError):
            chat_id = None
        stored_roy = bool(entry.get("roy_in"))
        stored_josh = bool(entry.get("josh_in"))
        _titles, cache_roy, cache_josh = load_peer_folder_titles()
        if chat_id is not None:
            stored_roy = stored_roy or chat_id in cache_roy
            stored_josh = stored_josh or chat_id in cache_josh
        form_sent = _form_ok(str(entry.get("form") or "")) or form_already_sent(
            config, rid=rid, chat_id=chat_id
        )
        snapshot = {
            "chat_id": chat_id,
            "chat_title": str(entry.get("chat_title") or ""),
            "project_name": str(entry.get("project_name") or ""),
            "stored_roy": stored_roy,
            "stored_josh": stored_josh,
            "form_sent": form_sent,
            "cache_roy": chat_id in cache_roy if chat_id is not None else False,
            "cache_josh": chat_id in cache_josh if chat_id is not None else False,
        }
    self_in = False
    peer_live: bool | None = None
    if client is not None and snapshot["chat_id"] is not None:
        self_in, live_title = await account_in_chat(client, int(snapshot["chat_id"]))
        if live_title:
            snapshot["chat_title"] = live_title
        peer = "josh" if account_key(config) == "roy" else "roy"
        peer_live = await lookup_peer_in_chat(
            client, int(snapshot["chat_id"]), peer
        )
    roy_in, josh_in = merge_membership(
        self_key=account_key(config),
        self_in=self_in,
        stored_roy=bool(snapshot["stored_roy"]),
        stored_josh=bool(snapshot["stored_josh"]),
        peer_live=peer_live,
    )
    roy_in = roy_in or bool(snapshot.get("cache_roy"))
    josh_in = josh_in or bool(snapshot.get("cache_josh"))
    peer_known = peer_live is not None or (
        bool(snapshot["stored_josh"])
        if account_key(config) == "roy"
        else bool(snapshot["stored_roy"])
    )
    if snapshot["chat_id"] is not None and not peer_known:
        with _locked_state(path) as data:
            entry = _project_entry(data, rid)
            if entry.get("notify") != "sent":
                entry["notify"] = "scheduled"
                entry["roy_in"] = roy_in
                entry["josh_in"] = josh_in
                if snapshot["form_sent"]:
                    entry["form"] = "already_sent"
                    entry["form_sent"] = True
                if snapshot["chat_title"]:
                    entry["chat_title"] = snapshot["chat_title"]
        logger.info(
            "live-onboard defer notify %s until peer membership is confirmed",
            rid,
        )
        return
    case = classify_case(roy_in, josh_in)
    form_sent = bool(snapshot["form_sent"])
    with _locked_state(path) as data:
        entry = _project_entry(data, rid)
        if entry.get("notify") == "sent":
            return
        entry["roy_in"] = roy_in
        entry["josh_in"] = josh_in
        entry["case"] = case
        entry["form_sent"] = form_sent
        if form_sent and not _form_ok(str(entry.get("form") or "")):
            entry["form"] = "already_sent"
        if snapshot["chat_title"]:
            entry["chat_title"] = snapshot["chat_title"]
        entry["notify"] = "sending"
        snapshot_entry = dict(entry)
    try:
        notify = await _notify_lark(config, snapshot_entry, fields)
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
    """Check membership, send form if this account is in the group, ping Lark now."""
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
    key = account_key(config)
    peer_live: bool | None = None
    _cache_titles, cache_roy, cache_josh = load_peer_folder_titles()
    if chat_id is not None:
        peer = "josh" if key == "roy" else "roy"
        peer_live = await lookup_peer_in_chat(client, chat_id, peer)
    with _locked_state(path) as data:
        entry = _project_entry(data, rid)
        entry["project_name"] = name
        if chat_id is not None:
            entry["chat_id"] = chat_id
        if chat_title:
            entry["chat_title"] = chat_title
        roy_in, josh_in = merge_membership(
            self_key=key,
            self_in=in_group,
            stored_roy=bool(entry.get("roy_in"))
            or (chat_id is not None and chat_id in cache_roy),
            stored_josh=bool(entry.get("josh_in"))
            or (chat_id is not None and chat_id in cache_josh),
            peer_live=peer_live,
        )
        if chat_id is not None:
            roy_in = roy_in or chat_id in cache_roy
            josh_in = josh_in or chat_id in cache_josh
        entry["roy_in"] = roy_in
        entry["josh_in"] = josh_in
        entry[f"{key}_checked_at"] = now
        if _form_ok(form_status) or form_already_sent(
            config, rid=rid, chat_id=chat_id
        ):
            entry["form"] = (
                form_status if _form_ok(form_status) else "already_sent"
            )
            entry["form_by"] = key
            entry["form_sent"] = True
        elif not _form_ok(str(entry.get("form") or "")):
            entry["form"] = form_status
            entry["form_sent"] = False
        case = classify_case(roy_in, josh_in)
        entry["case"] = case
        if source not in _SKIP_NOTIFY_SOURCES and entry.get("notify") != "sent":
            if sends_lark_notify(config):
                should_notify = True
            elif str(entry.get("notify") or "") not in _RETRY_NOTIFY:
                entry["notify"] = "need_roy"
        out["case"] = case
        out["form"] = str(entry.get("form") or form_status)
        out["chat_id"] = entry.get("chat_id")
        out["chat_title"] = str(entry.get("chat_title") or "")

    if should_notify:
        asyncio.create_task(
            _finalize_notify(
                config,
                rid=rid,
                fields=fields,
                source=source,
                client=client,
            ),
            name=f"live-onboard-notify-{rid}",
        )
    return out


async def drain_pending_roy_notifies(
    config: Any, client: TelegramClient | None = None
) -> int:
    """Roy号补发 Josh 留下的通知，以及重启后停在 scheduled/sending 的条目。"""
    if not sends_lark_notify(config):
        return 0
    if not getattr(config, "workflow_live_onboard_enabled", False):
        return 0
    path = _state_path(config)
    with _locked_state(path) as data:
        pending = [
            rid
            for rid, entry in (data.get("projects") or {}).items()
            if isinstance(entry, dict)
            and str(entry.get("notify") or "") in _RETRY_NOTIFY
        ]
    if not pending:
        return 0
    from bot.workflow_live_trigger import _load_progress_records

    try:
        _token, records = await _load_progress_records(config)
    except Exception:
        logger.exception("live-onboard drain: failed to load Lark records")
        return 0
    by_id = {str(rec.get("record_id") or ""): rec for rec in records}
    queued = 0
    for rid in pending:
        rec = by_id.get(rid)
        if not rec:
            continue
        fields = rec.get("fields") or {}
        with _locked_state(path) as data:
            entry = _project_entry(data, rid)
            if str(entry.get("notify") or "") not in _RETRY_NOTIFY:
                continue
        asyncio.create_task(
            _finalize_notify(
                config,
                rid=rid,
                fields=fields,
                source="roy_drain",
                client=client,
            ),
            name=f"live-onboard-notify-{rid}",
        )
        queued += 1
        logger.info("live-onboard drain queued Lark ping for %s", rid)
    return queued


async def drain_assigned_form_sends(client: TelegramClient, config: Any) -> int:
    """Post live-form bubbles this account was assigned, and take back expired handoffs."""
    if not getattr(config, "workflow_enabled", False):
        return 0
    if not getattr(config, "workflow_google_form_url", ""):
        return 0
    from bot.workflow_form_claim import (
        claim_path_for,
        pending_form_sends,
        reclaim_expired_form_sends,
    )
    from bot.workflow_live_trigger import _load_progress_records

    key = account_key(config)
    path = claim_path_for(config)
    jobs = pending_form_sends(path, key)
    jobs.extend(reclaim_expired_form_sends(path, key))
    if not jobs:
        return 0
    try:
        token, _records = await _load_progress_records(config)
    except Exception:
        logger.exception("form speaker drain: failed to load Lark records")
        return 0
    sent_n = 0
    seen: set[str] = set()
    for job in jobs:
        rid = str(job.get("record_id") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        try:
            chat_id = int(job.get("chat_id") or 0)
        except (TypeError, ValueError):
            chat_id = 0
        if not chat_id:
            continue
        status = await _send_form_if_needed(
            client,
            config,
            token=token,
            rid=rid,
            name=str(job.get("project_name") or ""),
            chat_id=chat_id,
            chat_title=str(job.get("chat_title") or ""),
            source="form_speaker",
        )
        if status == "sent":
            sent_n += 1
            logger.info(
                "form speaker drain sent %r (%s) chat_id=%s by %s",
                job.get("project_name"),
                rid,
                chat_id,
                key,
            )
    return sent_n


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
            already_ok = _form_ok(form_status)
        if already_ok:
            continue
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
