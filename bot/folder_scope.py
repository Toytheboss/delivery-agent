"""Sync allowed group chat IDs from a Telegram folder (Dialog Filter)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from telethon import TelegramClient, utils
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import DialogFilter, DialogFilterChatlist

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

FOLDER_NUM_RE = re.compile(r"^(?P<prefix>.+?)\s*#\s*(?P<num>\d+)$", re.IGNORECASE)


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
    """Cached set of chat IDs belonging to the configured folder(s)."""

    def __init__(self, client: TelegramClient, config: AppConfig) -> None:
        self.client = client
        self.config = config
        self._chat_ids: set[int] = set()

    async def refresh(self) -> set[int]:
        names = await resolve_folder_names(
            self.client,
            self.config.folder_names,
            prefix=getattr(self.config, "folder_name_prefix", "Delivery"),
        )
        # Keep runtime list current when new folders appear
        for name in names:
            if name not in self.config.folder_names:
                self.config.folder_names.append(name)
        self._chat_ids = await fetch_folder_chat_ids(
            self.client,
            self.config.folder_names,
            prefix=getattr(self.config, "folder_name_prefix", "Delivery"),
        )
        return set(self._chat_ids)

    def contains(self, chat_id: int) -> bool:
        return chat_id in self._chat_ids

    @property
    def chat_ids(self) -> set[int]:
        return set(self._chat_ids)
