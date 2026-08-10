"""Auto-add newly joined Delivery-named groups into Telegram folders.

When all existing Delivery folders are full (~100 chats), optionally create
the next folder (Delivery #4, #5, ...) and keep using it.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telethon import events, utils
from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
from telethon.tl.types import (
    Channel,
    Chat,
    DialogFilter,
    DialogFilterChatlist,
    TextWithEntities,
)

from bot.folder_scope import _folder_title
from bot.group_welcome import title_matches_project

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAX_PER_FOLDER = 100
FOLDER_NUM_RE = re.compile(r"^(?P<prefix>.+?)\s*#\s*(?P<num>\d+)$", re.IGNORECASE)
_add_lock: asyncio.Lock | None = None
_add_lock_loop: asyncio.AbstractEventLoop | None = None


def _get_add_lock() -> asyncio.Lock:
    """Create/reuse a lock bound to the *current* running event loop.

    A module-level ``asyncio.Lock()`` at import time binds to the wrong loop
    when ``asyncio.run()`` starts a fresh loop (e.g. bot restart in-process).
    """
    global _add_lock, _add_lock_loop
    loop = asyncio.get_running_loop()
    if _add_lock is None or _add_lock_loop is not loop:
        _add_lock = asyncio.Lock()
        _add_lock_loop = loop
    return _add_lock


def _peer_key(peer: object) -> tuple:
    return (
        type(peer).__name__,
        getattr(peer, "channel_id", None),
        getattr(peer, "chat_id", None),
        getattr(peer, "user_id", None),
    )


def _is_group_or_channel(entity: object) -> bool:
    if isinstance(entity, Chat):
        return True
    if isinstance(entity, Channel):
        return bool(
            getattr(entity, "megagroup", False) or getattr(entity, "broadcast", False)
        )
    return False


def _folder_sort_key(name: str) -> tuple:
    m = FOLDER_NUM_RE.match((name or "").strip())
    if m:
        return (m.group("prefix").strip().lower(), int(m.group("num")))
    return ((name or "").lower(), 0)


def _next_folder_name(existing_names: list[str], prefix: str) -> str:
    """Return next name like 'Delivery #4' based on existing numbered folders."""
    prefix = (prefix or "Delivery").strip() or "Delivery"
    highest = 0
    for name in existing_names:
        m = FOLDER_NUM_RE.match((name or "").strip())
        if not m:
            continue
        if m.group("prefix").strip().lower() != prefix.lower():
            continue
        highest = max(highest, int(m.group("num")))
    return f"{prefix} #{highest + 1}"


def _remember_folder_name(config: AppConfig, folder_name: str) -> None:
    """Keep runtime + config.yaml folder_names in sync after creating a folder."""
    if folder_name not in config.folder_names:
        config.folder_names.append(folder_name)
    try:
        path = ROOT / "config" / "config.yaml"
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8")
        # Already listed
        if re.search(rf'^\s*-\s*["\']?{re.escape(folder_name)}["\']?\s*$', text, re.M):
            return
        lines = text.splitlines(keepends=True)
        out: list[str] = []
        in_folder_names = False
        inserted = False
        folder_indent = "    "
        for line in lines:
            if re.match(r"^  folder_names:\s*$", line):
                in_folder_names = True
                out.append(line)
                continue
            if in_folder_names:
                m = re.match(r"^(\s+)-\s+", line)
                if m:
                    folder_indent = m.group(1)
                    out.append(line)
                    continue
                # end of list — insert before this line
                if not inserted:
                    out.append(f'{folder_indent}- "{folder_name}"\n')
                    inserted = True
                in_folder_names = False
            out.append(line)
        if in_folder_names and not inserted:
            out.append(f'{folder_indent}- "{folder_name}"\n')
            inserted = True
        if inserted:
            path.write_text("".join(out), encoding="utf-8")
            logger.info("folder_auto_add: persisted %r into config.yaml", folder_name)
    except Exception:
        logger.exception(
            "folder_auto_add: failed to persist folder name %r to config.yaml",
            folder_name,
        )


async def discover_project_folders(
    client: TelegramClient,
    *,
    configured_names: list[str] | None = None,
    prefix: str = "Delivery",
) -> list[tuple[str, int, object]]:
    """Return Delivery folders (configured + any Telegram folders matching Prefix #N)."""
    result = await client(GetDialogFiltersRequest())
    prefix_l = (prefix or "Delivery").strip().lower()
    configured = set(configured_names or [])

    found: dict[str, tuple[str, int, object]] = {}
    for item in result.filters or []:
        title = _folder_title(item)
        fid = getattr(item, "id", None)
        if not title or not isinstance(fid, int):
            continue
        if title in configured:
            found[title] = (title, fid, item)
            continue
        m = FOLDER_NUM_RE.match(title.strip())
        if m and m.group("prefix").strip().lower() == prefix_l:
            found[title] = (title, fid, item)

    out = list(found.values())
    out.sort(key=lambda x: _folder_sort_key(x[0]))
    return out


async def _allocate_folder_id(client: TelegramClient) -> int:
    result = await client(GetDialogFiltersRequest())
    used: set[int] = set()
    for item in result.filters or []:
        fid = getattr(item, "id", None)
        if isinstance(fid, int):
            used.add(fid)
    for candidate in range(2, 256):
        if candidate not in used:
            return candidate
    raise RuntimeError("No free Telegram folder id available (2..255)")


async def _folder_peer_ids(
    client: TelegramClient, folder_item: object
) -> tuple[set[int], list[Any], list[Any]]:
    pinned_raw = list(getattr(folder_item, "pinned_peers", []) or [])
    include_raw = list(getattr(folder_item, "include_peers", []) or [])
    chat_ids: set[int] = set()
    pinned_peers: list[Any] = []
    include_peers: list[Any] = []

    for peer in pinned_raw:
        try:
            entity = await client.get_entity(peer)
            chat_ids.add(utils.get_peer_id(entity))
            pinned_peers.append(await client.get_input_entity(entity))
        except Exception:  # noqa: BLE001
            continue
    for peer in include_raw:
        try:
            entity = await client.get_entity(peer)
            chat_ids.add(utils.get_peer_id(entity))
            include_peers.append(await client.get_input_entity(entity))
        except Exception:  # noqa: BLE001
            continue
    return chat_ids, pinned_peers, include_peers


async def _write_folder(
    client: TelegramClient,
    *,
    folder_id: int,
    folder_name: str,
    existing: object | None,
    pinned_peers: list[Any],
    include_peers: list[Any],
) -> None:
    peer_keys: set[tuple] = set()
    unique_include: list[Any] = []
    for peer in list(pinned_peers) + list(include_peers):
        key = _peer_key(peer)
        if key in peer_keys:
            continue
        peer_keys.add(key)
        unique_include.append(peer)

    title = TextWithEntities(text=folder_name, entities=[])
    emoticon = getattr(existing, "emoticon", None) if existing is not None else None
    color = getattr(existing, "color", None) if existing is not None else None

    if isinstance(existing, DialogFilterChatlist):
        new_filter: object = DialogFilterChatlist(
            id=folder_id,
            title=title,
            pinned_peers=pinned_peers,
            include_peers=unique_include,
            emoticon=emoticon,
            color=color,
        )
    else:
        new_filter = DialogFilter(
            id=folder_id,
            title=title,
            pinned_peers=pinned_peers,
            include_peers=unique_include,
            exclude_peers=[],
            contacts=False,
            non_contacts=False,
            groups=False,
            broadcasts=False,
            bots=False,
            emoticon=emoticon,
            color=color,
        )

    ok = await client(UpdateDialogFilterRequest(id=folder_id, filter=new_filter))
    if not ok:
        raise RuntimeError(f"UpdateDialogFilterRequest failed for {folder_name!r}")


async def _resolve_live_chat(
    client: TelegramClient, chat: object
) -> tuple[object, int, Any]:
    """Prefer migrated megagroup when a basic Chat was upgraded/deactivated."""
    migrated = getattr(chat, "migrated_to", None)
    if migrated is not None or getattr(chat, "deactivated", False):
        try:
            if migrated is not None:
                live = await client.get_entity(migrated)
            else:
                live = await client.get_entity(chat)
            return live, utils.get_peer_id(live), await client.get_input_entity(live)
        except Exception:
            logger.warning(
                "folder_auto_add: failed to resolve migrated chat for %r; using original",
                getattr(chat, "title", None),
            )
    return chat, utils.get_peer_id(chat), await client.get_input_entity(chat)


async def ensure_chat_in_folders(
    client: TelegramClient,
    config: AppConfig,
    chat: object,
    *,
    scope: FolderScope | None = None,
    title: str | None = None,
) -> str | None:
    """Add chat to first free Delivery folder; create a new folder if all are full."""
    if not config.folder_auto_add_enabled:
        return None

    chat_title = title if title is not None else (getattr(chat, "title", None) or "")
    keywords = config.folder_auto_add_keywords or config.welcome_name_keywords
    if not title_matches_project(chat_title, keywords):
        return None

    try:
        chat, chat_id, input_peer = await _resolve_live_chat(client, chat)
        chat_title = getattr(chat, "title", None) or chat_title
    except Exception:
        logger.exception("folder_auto_add: cannot resolve chat %r", chat_title)
        return None

    max_per = max(int(config.folder_max_chats or DEFAULT_MAX_PER_FOLDER), 1)
    prefix = (config.folder_name_prefix or "Delivery").strip() or "Delivery"

    async with _get_add_lock():
        folders = await discover_project_folders(
            client,
            configured_names=list(config.folder_names or []),
            prefix=prefix,
        )
        # Sync any discovered folders into runtime config
        for name, _fid, _item in folders:
            if name not in config.folder_names:
                config.folder_names.append(name)

        folder_states: list[tuple[str, int, object, set[int], list[Any], list[Any]]] = []
        for name, fid, item in folders:
            ids, pinned, include = await _folder_peer_ids(client, item)
            folder_states.append((name, fid, item, ids, pinned, include))
            if chat_id in ids:
                logger.debug(
                    "folder_auto_add: chat_id=%s already in %r", chat_id, name
                )
                return None

        target = None
        for name, fid, item, ids, pinned, include in folder_states:
            if len(ids) < max_per:
                target = (name, fid, item, ids, pinned, include)
                break

        if target is None:
            if not config.folder_auto_create_enabled:
                logger.warning(
                    "folder_auto_add: all folders full (max=%d); "
                    "auto-create disabled; cannot add chat_id=%s %r",
                    max_per,
                    chat_id,
                    chat_title,
                )
                return None

            existing_names = [n for n, *_ in folder_states] or list(config.folder_names)
            new_name = _next_folder_name(existing_names, prefix)
            new_id = await _allocate_folder_id(client)
            await _write_folder(
                client,
                folder_id=new_id,
                folder_name=new_name,
                existing=None,
                pinned_peers=[],
                include_peers=[input_peer],
            )
            _remember_folder_name(config, new_name)
            logger.info(
                "folder_auto_add: created %r (id=%s) and added chat_id=%s %r",
                new_name,
                new_id,
                chat_id,
                chat_title,
            )
            name = new_name
        else:
            name, fid, item, _ids, pinned, include = target
            include = list(include) + [input_peer]
            await _write_folder(
                client,
                folder_id=fid,
                folder_name=name,
                existing=item,
                pinned_peers=pinned,
                include_peers=include,
            )
            logger.info(
                "folder_auto_add: added chat_id=%s %r -> %r",
                chat_id,
                chat_title,
                name,
            )

    if scope is not None:
        try:
            await scope.refresh()
        except Exception:
            logger.exception("folder_auto_add: scope refresh failed")

    try:
        from bot.metrics import inc

        inc("folder_auto_add_success")
    except Exception:  # noqa: BLE001
        pass
    return name


async def scan_and_add_missing(
    client: TelegramClient,
    config: AppConfig,
    *,
    scope: FolderScope | None = None,
) -> int:
    """Scan dialogs and add any Delivery-titled groups missing from folders."""
    if not config.folder_auto_add_enabled:
        return 0

    keywords = config.folder_auto_add_keywords or config.welcome_name_keywords
    added = 0
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not _is_group_or_channel(entity):
            continue
        title = getattr(entity, "title", None) or ""
        if not title_matches_project(title, keywords):
            continue
        name = await ensure_chat_in_folders(
            client, config, entity, scope=None, title=title
        )
        if name:
            added += 1
            await asyncio.sleep(0.35)

    if added and scope is not None:
        try:
            await scope.refresh()
        except Exception:
            logger.exception("folder_auto_add: scope refresh after scan failed")
    return added


def register_folder_auto_add_handlers(
    client: TelegramClient,
    config: AppConfig,
    my_id: int,
    *,
    scope: FolderScope | None = None,
) -> None:
    """On join, immediately pull matching groups into a Delivery folder."""

    @client.on(events.ChatAction)
    async def _on_chat_action(event: events.ChatAction.Event) -> None:
        if not config.folder_auto_add_enabled:
            return
        added_me = False
        if event.user_added or event.created:
            user_ids = list(event.user_ids or [])
            if event.user_id:
                user_ids.append(event.user_id)
            if my_id in user_ids:
                added_me = True
        if getattr(event, "user_joined", False) and event.user_id == my_id:
            added_me = True
        if not added_me:
            return

        try:
            chat = await event.get_chat()
        except Exception:  # noqa: BLE001
            logger.exception("folder_auto_add: get_chat failed")
            return
        title = getattr(chat, "title", None) or ""
        await asyncio.sleep(0.5)
        await ensure_chat_in_folders(
            client, config, chat, scope=scope, title=title
        )


async def folder_auto_add_loop(
    client: TelegramClient,
    config: AppConfig,
    *,
    scope: FolderScope | None = None,
) -> None:
    interval = max(int(config.folder_auto_add_scan_minutes or 2), 1) * 60
    while True:
        await asyncio.sleep(interval)
        try:
            n = await scan_and_add_missing(client, config, scope=scope)
            if n:
                logger.info("folder_auto_add scan added %d chat(s)", n)
        except Exception:
            logger.exception("folder_auto_add scan failed")
