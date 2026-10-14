"""Auto-add newly joined Delivery-named groups into Telegram folders.

When all existing Delivery folders are full (~100 chats), optionally create
the next folder (Delivery #4, #5, ...) and keep using it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telethon import events, utils
from telethon.errors import BadRequestError
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


def _is_stale_upgraded_chat(entity: object) -> bool:
    """Leftover basic Chat after Telegram upgraded the group to a megagroup.

    The dialog list still shows the deactivated id; the live ``-100…`` chat is
    a different peer and is what belongs in the Folder.
    """
    return bool(getattr(entity, "deactivated", False))


def inactive_on_or_before(when: datetime | None, cutoff: str) -> bool:
    """True when the last message falls on the cutoff date or earlier (UTC+8)."""
    text = (cutoff or "").strip()
    if not text or when is None:
        return False
    limit = datetime.strptime(text[:10], "%Y-%m-%d").date()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        local = when.astimezone(ZoneInfo("Asia/Shanghai"))
    except Exception:  # noqa: BLE001
        local = when.astimezone(timezone(timedelta(hours=8)))
    return local.date() <= limit


_ACTIVITY_TTL_SECONDS = 30 * 60
_PEER_DATA_DIRS = (
    Path("/opt/botchain-qa-tg-bot/data"),
    Path("/opt/delivery-agent/data"),
)
_activity_cache: tuple[float, dict[int, datetime]] | None = None


def _parse_ts(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _absorb_activity(path: Path, found: dict[int, datetime]) -> None:
    try:
        handle = path.open(encoding="utf-8", errors="ignore")
    except OSError:
        return
    with handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                chat_id = int(row.get("chat_id"))
            except (TypeError, ValueError):
                continue
            when = _parse_ts(row.get("ts"))
            if when is not None and when > found.get(chat_id, when - timedelta(seconds=1)):
                found[chat_id] = when


def _activity_by_chat() -> dict[int, datetime]:
    """Last seen time per chat, from both bots' message logs and workflow events."""
    global _activity_cache
    now_mono = time.monotonic()
    if _activity_cache and now_mono - _activity_cache[0] < _ACTIVITY_TTL_SECONDS:
        return _activity_cache[1]
    roots: list[Path] = []
    for raw in (ROOT / "data", *_PEER_DATA_DIRS):
        try:
            resolved = raw.resolve()
        except OSError:
            continue
        if resolved in roots or not resolved.is_dir():
            continue
        roots.append(resolved)
    found: dict[int, datetime] = {}
    for root in roots:
        logs = sorted((root / "message_logs").glob("messages-*.jsonl"))[-70:]
        for path in logs:
            _absorb_activity(path, found)
        events = root / "workflow_events.jsonl"
        if events.is_file():
            _absorb_activity(events, found)
    _activity_cache = (now_mono, found)
    return found


def _peer_folder_chat_ids() -> set[int] | None:
    """Chats the other bot still keeps in its folders, or None when unknown."""
    try:
        own = (ROOT / "data").resolve()
    except OSError:
        own = None
    found = False
    ids: set[int] = set()
    for raw in _PEER_DATA_DIRS:
        try:
            if own is not None and raw.resolve() == own:
                continue
        except OSError:
            continue
        path = raw / "folder_title_cache.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        titles = payload.get("titles") if isinstance(payload, dict) else None
        if not isinstance(titles, dict):
            continue
        found = True
        for key in titles:
            try:
                ids.add(int(key))
            except (TypeError, ValueError):
                continue
    return ids if found else None


def select_rotate_chat_ids(
    entries: list[tuple[int, datetime | None]],
    *,
    pinned_ids: set[int],
    peer_ids: set[int] | None,
    now: datetime,
    inactive_days: int,
    limit: int,
) -> list[int]:
    """Oldest chats quiet for ``inactive_days``, skipping pinned and peer-only copies."""
    if limit <= 0:
        return []
    cutoff = now - timedelta(days=max(int(inactive_days), 1))
    never = datetime.min.replace(tzinfo=timezone.utc)
    eligible: list[tuple[datetime, int]] = []
    for chat_id, last in entries:
        if chat_id in pinned_ids:
            continue
        if peer_ids is not None and chat_id not in peer_ids:
            continue
        if last is not None and last >= cutoff:
            continue
        eligible.append((last or never, chat_id))
    eligible.sort()
    return [chat_id for _, chat_id in eligible[:limit]]


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
    """Collect peer IDs without GetChatsRequest when peers are already InputPeer*."""
    from bot.tg_rate_limit import paced_get_entity

    pinned_raw = list(getattr(folder_item, "pinned_peers", []) or [])
    include_raw = list(getattr(folder_item, "include_peers", []) or [])
    chat_ids: set[int] = set()
    pinned_peers: list[Any] = []
    include_peers: list[Any] = []

    async def _absorb(peer: object, dest: list[Any]) -> None:
        try:
            chat_ids.add(utils.get_peer_id(peer))
            dest.append(peer)
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            entity = await paced_get_entity(client, peer)
            chat_ids.add(utils.get_peer_id(entity))
            dest.append(await client.get_input_entity(entity))
        except Exception:  # noqa: BLE001
            return

    for peer in pinned_raw:
        await _absorb(peer, pinned_peers)
    for peer in include_raw:
        await _absorb(peer, include_peers)
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


def _filters_full(exc: BaseException) -> bool:
    return "DIALOG_FILTERS_TOO_MUCH" in str(exc)


async def _load_folder_states(
    client: TelegramClient, config: AppConfig
) -> list[tuple[str, int, object, set[int], list[Any], list[Any]]]:
    prefix = (config.folder_name_prefix or "Delivery").strip() or "Delivery"
    folders = await discover_project_folders(
        client,
        configured_names=list(config.folder_names or []),
        prefix=prefix,
    )
    states: list[tuple[str, int, object, set[int], list[Any], list[Any]]] = []
    for name, fid, item in folders:
        if name not in config.folder_names:
            config.folder_names.append(name)
        ids, pinned, include = await _folder_peer_ids(client, item)
        states.append((name, fid, item, ids, pinned, include))
    return states


async def release_stale_chats(
    client: TelegramClient,
    config: AppConfig,
    states: list[tuple[str, int, object, set[int], list[Any], list[Any]]],
    *,
    need: int,
) -> int:
    """Drop the quietest chats so a full account can take new groups."""
    if not config.folder_auto_rotate_enabled or need <= 0:
        return 0
    limit = min(max(int(need), 1), max(int(config.folder_auto_rotate_max_per_scan), 1))
    pinned_ids: set[int] = set()
    entries: list[tuple[int, datetime | None]] = []
    owner: dict[int, int] = {}
    activity = _activity_by_chat()
    for index, (_name, _fid, _item, ids, pinned, _include) in enumerate(states):
        for peer in pinned:
            try:
                pinned_ids.add(utils.get_peer_id(peer))
            except Exception:  # noqa: BLE001
                continue
        for chat_id in ids:
            if chat_id in owner:
                continue
            owner[chat_id] = index
            entries.append((chat_id, activity.get(chat_id)))
    chosen = select_rotate_chat_ids(
        entries,
        pinned_ids=pinned_ids,
        peer_ids=_peer_folder_chat_ids(),
        now=datetime.now(timezone.utc),
        inactive_days=config.folder_auto_rotate_inactive_days,
        limit=limit,
    )
    if not chosen:
        logger.info("folder_auto_add: folders full but nothing quiet enough to rotate")
        return 0
    drop = set(chosen)
    removed = 0
    for name, fid, item, ids, pinned, include in states:
        gone = ids & drop
        if not gone:
            continue
        kept = [
            peer
            for peer in include
            if _peer_id_or_none(peer) not in gone
        ]
        await _write_folder(
            client,
            folder_id=fid,
            folder_name=name,
            existing=item,
            pinned_peers=pinned,
            include_peers=kept,
        )
        removed += len(gone)
        logger.info(
            "folder_auto_add: rotated %d quiet chat(s) out of %r", len(gone), name
        )
        await asyncio.sleep(0.4)
    return removed


def _peer_id_or_none(peer: object) -> int | None:
    try:
        return utils.get_peer_id(peer)
    except Exception:  # noqa: BLE001
        return None


async def maintain_folder_room(client: TelegramClient, config: AppConfig) -> int:
    """Rotate when free slots across all folders drop below the target."""
    if not config.folder_auto_rotate_enabled:
        return 0
    states = await _load_folder_states(client, config)
    if not states:
        return 0
    max_per = max(int(config.folder_max_chats or DEFAULT_MAX_PER_FOLDER), 1)
    free = sum(max(max_per - len(ids), 0) for _n, _f, _i, ids, _p, _c in states)
    gap = int(config.folder_auto_rotate_keep_free) - free
    if gap <= 0:
        return 0
    return await release_stale_chats(client, config, states, need=gap)


async def _resolve_live_chat(
    client: TelegramClient, chat: object
) -> tuple[object, int, Any]:
    """Prefer migrated megagroup when a basic Chat was upgraded/deactivated.

    Never fall back to a deactivated leftover id — that peer does not belong
    in a Folder and the live megagroup is usually already there.
    """
    migrated = getattr(chat, "migrated_to", None)
    stale = _is_stale_upgraded_chat(chat)
    if migrated is not None or stale:
        try:
            if migrated is not None:
                live = await client.get_entity(migrated)
            else:
                live = await client.get_entity(chat)
            if _is_stale_upgraded_chat(live):
                raise RuntimeError("resolved entity is still deactivated")
            return live, utils.get_peer_id(live), await client.get_input_entity(live)
        except Exception:
            logger.warning(
                "folder_auto_add: failed to resolve migrated chat for %r; skip",
                getattr(chat, "title", None),
            )
            if stale:
                raise
    return chat, utils.get_peer_id(chat), await client.get_input_entity(chat)


async def ensure_chat_in_folders(
    client: TelegramClient,
    config: AppConfig,
    chat: object,
    *,
    scope: FolderScope | None = None,
    title: str | None = None,
    last_message_at: datetime | None = None,
) -> str | None:
    """Add chat to first free Delivery folder; create a new folder if all are full."""
    if not config.folder_auto_add_enabled:
        return None

    chat_title = title if title is not None else (getattr(chat, "title", None) or "")
    keywords = config.folder_auto_add_keywords or config.welcome_name_keywords
    if not title_matches_project(chat_title, keywords):
        return None
    cutoff = str(getattr(config, "folder_inactive_before", "") or "")
    if inactive_on_or_before(last_message_at, cutoff):
        logger.info(
            "folder_auto_add: skip inactive %r cutoff=%s",
            chat_title,
            cutoff,
        )
        return None
    if _is_stale_upgraded_chat(chat) and getattr(chat, "migrated_to", None) is None:
        logger.debug(
            "folder_auto_add: skip deactivated chat with no migrate target %r",
            chat_title,
        )
        return None

    try:
        chat, chat_id, input_peer = await _resolve_live_chat(client, chat)
        chat_title = getattr(chat, "title", None) or chat_title
    except Exception:
        logger.exception("folder_auto_add: cannot resolve chat %r", chat_title)
        return None
    if _is_stale_upgraded_chat(chat):
        logger.debug("folder_auto_add: skip still-deactivated chat %r", chat_title)
        return None

    if chat_title:
        try:
            from bot.workflow_form_dispatch import remember_chat_title

            remember_chat_title(chat_id, chat_title)
        except Exception:  # noqa: BLE001
            pass

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

        def _with_room() -> tuple | None:
            for state in folder_states:
                if len(state[3]) < max_per:
                    return state
            return None

        target = _with_room()
        if target is None and config.folder_auto_rotate_enabled:
            freed = await release_stale_chats(
                client,
                config,
                folder_states,
                need=config.folder_auto_rotate_keep_free,
            )
            if freed:
                folder_states = await _load_folder_states(client, config)
                for _name, _fid, _item, ids, _pinned, _include in folder_states:
                    if chat_id in ids:
                        return None
                target = _with_room()

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
            try:
                await _write_folder(
                    client,
                    folder_id=new_id,
                    folder_name=new_name,
                    existing=None,
                    pinned_peers=[],
                    include_peers=[input_peer],
                )
            except BadRequestError as exc:
                if not _filters_full(exc):
                    raise
                logger.warning(
                    "folder_auto_add: Telegram folder limit reached; rotating quiet chats"
                )
                freed = await release_stale_chats(
                    client,
                    config,
                    folder_states,
                    need=config.folder_auto_rotate_keep_free,
                )
                if not freed:
                    return None
                folder_states = await _load_folder_states(client, config)
                target = _with_room()
                if target is None:
                    return None
            else:
                _remember_folder_name(config, new_name)
                logger.info(
                    "folder_auto_add: created %r (id=%s) and added chat_id=%s %r",
                    new_name,
                    new_id,
                    chat_id,
                    chat_title,
                )
                name = new_name
                target = None
        if target is not None:
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
    try:
        from bot.workflow_events import log_delivery

        log_delivery(
            "folder_chat_added",
            "folder_auto_add",
            project_name=str(chat_title or ""),
            chat_id=chat_id,
            text=f"已将项目群加入 Folder：{chat_title}",
        )
    except Exception:
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

    from bot.tg_rate_limit import tg_heavy_section
    from bot.workflow_form_dispatch import remember_chat_title

    keywords = config.folder_auto_add_keywords or config.welcome_name_keywords
    added = 0
    try:
        await maintain_folder_room(client, config)
    except Exception:
        logger.exception("folder_auto_add: rotate before scan failed")
    async with tg_heavy_section():
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not _is_group_or_channel(entity):
                continue
            if _is_stale_upgraded_chat(entity):
                continue
            title = getattr(entity, "title", None) or ""
            if not title_matches_project(title, keywords):
                continue
            try:
                chat_id = utils.get_peer_id(entity)
                if title:
                    remember_chat_title(chat_id, title)
            except Exception:  # noqa: BLE001
                pass
            name = await ensure_chat_in_folders(
                client,
                config,
                entity,
                scope=None,
                title=title,
                last_message_at=getattr(dialog, "date", None),
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
        last_at = None
        try:
            latest = await client.get_messages(chat, limit=1)
            if latest:
                last_at = getattr(latest[0], "date", None)
        except Exception:  # noqa: BLE001
            logger.debug("folder_auto_add: last message lookup failed for %r", title)
        await ensure_chat_in_folders(
            client, config, chat, scope=scope, title=title, last_message_at=last_at
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
