"""Working set of groups this account has joined.

Telegram folders stay as a way to file chats in the client. Automation
(replies, form matching, onboard) follows membership, not folder placement.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from telethon import TelegramClient, utils
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import DialogFilter, DialogFilterChatlist

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

FOLDER_NUM_RE = re.compile(r"^(?P<prefix>.+?)\s*#\s*(?P<num>\d+)$", re.IGNORECASE)


def chat_in_joined_scope(
    chat_id: int,
    *,
    is_group: bool,
    deactivated: bool,
    broadcast_only: bool,
    ignored: set[int],
) -> bool:
    """True for a live group this account belongs to and has not ignored."""
    if not is_group or deactivated or broadcast_only:
        return False
    return chat_id not in ignored


def select_project_chats(
    titles: dict[int, str], keywords: list[str]
) -> dict[int, str]:
    """Keep joined groups whose title matches the project keywords."""
    from bot.group_welcome import title_matches_project

    return {
        chat_id: title
        for chat_id, title in titles.items()
        if title_matches_project(title, keywords)
    }


def _sync_title_cache(titles: dict[int, str]) -> None:
    """Rewrite the on-disk title cache so it matches current membership."""
    path = ROOT / "data" / "folder_title_cache.json"
    now = time.time()
    payload = {
        "titles": {
            str(chat_id): {"title": title, "ts": now}
            for chat_id, title in titles.items()
            if str(title or "").strip()
        }
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        logger.exception("Failed to persist joined-group title cache")


async def fetch_joined_group_ids(
    client: TelegramClient, *, ignored: set[int] | None = None
) -> tuple[set[int], dict[int, str]]:
    """Every live group/supergroup dialog, skipping broadcasts and ignored ids."""
    from bot.folder_auto_add import _is_group_or_channel, _is_stale_upgraded_chat
    from bot.tg_rate_limit import tg_heavy_section

    skipped = set(ignored or ())
    chat_ids: set[int] = set()
    titles: dict[int, str] = {}
    async with tg_heavy_section():
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            is_group = _is_group_or_channel(entity)
            deactivated = _is_stale_upgraded_chat(entity)
            broadcast_only = bool(
                getattr(entity, "broadcast", False)
                and not getattr(entity, "megagroup", False)
            )
            try:
                chat_id = utils.get_peer_id(entity)
            except Exception:  # noqa: BLE001
                continue
            if not chat_in_joined_scope(
                chat_id,
                is_group=is_group,
                deactivated=deactivated,
                broadcast_only=broadcast_only,
                ignored=skipped,
            ):
                continue
            chat_ids.add(chat_id)
            title = str(
                getattr(dialog, "title", None) or getattr(entity, "title", None) or ""
            ).strip()
            if title:
                titles[chat_id] = title
    logger.info("Joined groups in scope: %d", len(chat_ids))
    return chat_ids, titles


def _folder_title(item: object) -> str | None:
    title = getattr(item, "title", None)
    if title is None:
        return None
    if isinstance(title, str):
        return title
    return getattr(title, "text", None)


async def resolve_folder_names(
    client: TelegramClient,
    folder_names: str | list[str],
    *,
    prefix: str = "Delivery",
) -> list[str]:
    """Configured names plus any live Telegram folders matching ``Prefix #N``."""
    names = [folder_names] if isinstance(folder_names, str) else list(folder_names)
    names = [n for n in names if n]
    prefix_l = (prefix or "Delivery").strip().lower()
    result = await client(GetDialogFiltersRequest())
    discovered: list[str] = []
    for item in result.filters or []:
        title = _folder_title(item)
        if not title:
            continue
        if title in names:
            continue
        m = FOLDER_NUM_RE.match(title.strip())
        if m and m.group("prefix").strip().lower() == prefix_l:
            discovered.append(title)
    merged = list(names)
    for title in discovered:
        if title not in merged:
            merged.append(title)
    return merged


async def fetch_folder_chat_ids(
    client: TelegramClient,
    folder_names: str | list[str],
    *,
    prefix: str = "Delivery",
) -> set[int]:
    """Return chat IDs for groups/channels in configured / discovered folders.

    Prefer ``utils.get_peer_id(peer)`` (no network). Only call get_entity when
    the peer cannot be converted locally — critical as folder size grows.
    """
    from bot.tg_rate_limit import paced_get_entity, tg_heavy_section

    names = await resolve_folder_names(client, folder_names, prefix=prefix)
    if not names:
        return set()

    result = await client(GetDialogFiltersRequest())
    filters = result.filters or []

    targets: list[tuple[str, object]] = []
    found: set[str] = set()
    for item in filters:
        title = _folder_title(item)
        if title in names:
            targets.append((title, item))
            found.add(title)

    for name in names:
        if name not in found:
            logger.warning("Telegram folder %r not found", name)

    if not targets:
        return set()

    chat_ids: set[int] = set()
    resolve_needed = 0
    async with tg_heavy_section():
        for folder_name, target in targets:
            peer_lists: list = []
            if isinstance(target, (DialogFilter, DialogFilterChatlist)):
                peer_lists.extend(getattr(target, "include_peers", []) or [])
                peer_lists.extend(getattr(target, "pinned_peers", []) or [])

            before = len(chat_ids)
            for peer in peer_lists:
                cid: int | None = None
                try:
                    cid = utils.get_peer_id(peer)
                except Exception:
                    cid = None
                if cid is not None:
                    chat_ids.add(cid)
                    continue
                resolve_needed += 1
                try:
                    entity = await paced_get_entity(client, peer)
                    chat_ids.add(utils.get_peer_id(entity))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Could not resolve peer in folder %r: %s", folder_name, exc
                    )
            logger.info(
                "Folder %r contributes %d chat(s)",
                folder_name,
                len(chat_ids) - before,
            )

    if resolve_needed:
        logger.info(
            "Folder peer resolve used get_entity for %d peer(s); rest were local",
            resolve_needed,
        )
    logger.info(
        "Folders %s contain %d unique chat(s)",
        names,
        len(chat_ids),
    )
    return chat_ids


class FolderScope:
    """Cached set of group chat IDs this account has joined."""

    def __init__(self, client: TelegramClient, config: AppConfig) -> None:
        self.client = client
        self.config = config
        self._chat_ids: set[int] = set()

    async def refresh(self) -> set[int]:
        ignored = set(getattr(self.config, "ignored_group_ids", set()) or set())
        _joined, titles = await fetch_joined_group_ids(self.client, ignored=ignored)
        keywords = list(
            getattr(self.config, "folder_auto_add_keywords", None)
            or getattr(self.config, "welcome_name_keywords", None)
            or []
        )
        project = select_project_chats(titles, keywords)
        logger.info(
            "Project groups in scope: %d (joined groups %d)",
            len(project),
            len(_joined),
        )
        self._chat_ids = set(project)
        _sync_title_cache(project)
        return set(self._chat_ids)

    def contains(self, chat_id: int) -> bool:
        return chat_id in self._chat_ids

    @property
    def chat_ids(self) -> set[int]:
        return set(self._chat_ids)
