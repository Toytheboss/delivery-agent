#!/usr/bin/env python3
"""Distribute Delivery-named group chats across Delivery Telegram folders.

Telegram folders allow at most ~100 chats each. This script finds all
group/channel dialogs whose title contains "partner" or "delivery",
then fills configured folders in order (100 per folder).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from telethon import TelegramClient, utils
from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
from telethon.tl.types import (
    Channel,
    Chat,
    DialogFilter,
    DialogFilterChatlist,
    TextWithEntities,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config_loader import load_config
from bot.folder_scope import _folder_title

DEFAULT_FOLDERS = ["Delivery #1", "Delivery #2", "Delivery #3"]
MAX_PER_FOLDER = 100
TITLE_RE = re.compile(r"bot\s*chain", re.IGNORECASE)


def _proxy_tuple():
    raw = os.getenv("TELEGRAM_PROXY", "").strip()
    if not raw:
        return None
    p = urlparse(raw)
    return p.scheme.lower(), p.hostname, p.port or 7897


def _title_of(entity) -> str:
    return (getattr(entity, "title", None) or getattr(entity, "first_name", "") or "").strip()


def _is_group_or_channel(entity) -> bool:
    if isinstance(entity, Chat):
        return True
    if isinstance(entity, Channel):
        return bool(getattr(entity, "megagroup", False) or getattr(entity, "broadcast", False))
    return False


def title_matches_project(title: str) -> bool:
    return bool(TITLE_RE.search(title or ""))


async def find_matching_dialogs(client: TelegramClient) -> list[tuple[int, str, object]]:
    matches: list[tuple[int, str, object]] = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not _is_group_or_channel(entity):
            continue
        title = _title_of(entity)
        if not title_matches_project(title):
            continue
        chat_id = utils.get_peer_id(entity)
        matches.append((chat_id, title, entity))
    matches.sort(key=lambda x: x[1].lower())
    return matches


async def list_folders(client: TelegramClient) -> list[tuple[str, int, object]]:
    result = await client(GetDialogFiltersRequest())
    out: list[tuple[str, int, object]] = []
    for item in result.filters or []:
        title = _folder_title(item)
        fid = getattr(item, "id", None)
        if title and isinstance(fid, int):
            out.append((title, fid, item))
    return out


async def get_or_create_folder(
    client: TelegramClient,
    folder_name: str,
    existing_folders: list[tuple[str, int, object]],
) -> tuple[int, object | None]:
    for title, fid, item in existing_folders:
        if title == folder_name:
            return fid, item

    used_ids = {fid for _, fid, _ in existing_folders}
    for candidate in range(2, 256):
        if candidate not in used_ids:
            return candidate, None
    raise RuntimeError("No free Telegram folder id available")


async def build_include_peers(client: TelegramClient, entities: list[object]) -> list:
    peers = []
    for entity in entities:
        try:
            peers.append(await client.get_input_entity(entity))
        except Exception as exc:  # noqa: BLE001
            print(f"  skip resolve failed: {_title_of(entity)!r} ({exc})")
    return peers


def _peer_key(peer) -> tuple:
    return (
        type(peer).__name__,
        getattr(peer, "channel_id", None),
        getattr(peer, "chat_id", None),
        getattr(peer, "user_id", None),
    )


async def update_folder(
    client: TelegramClient,
    folder_id: int,
    folder_name: str,
    existing,
    include_peers: list,
) -> None:
    pinned_peers = []
    if existing is not None:
        for peer in getattr(existing, "pinned_peers", []) or []:
            try:
                pinned_peers.append(await client.get_input_entity(peer))
            except Exception:  # noqa: BLE001
                continue

    # Keep only pins that are still part of this folder's assignment
    include_keys = {_peer_key(p) for p in include_peers}
    pinned_peers = [p for p in pinned_peers if _peer_key(p) in include_keys]

    peer_keys = set()
    unique_include = []
    for peer in list(pinned_peers) + list(include_peers):
        key = _peer_key(peer)
        if key in peer_keys:
            continue
        peer_keys.add(key)
        unique_include.append(peer)

    if len(unique_include) > MAX_PER_FOLDER:
        raise RuntimeError(
            f"Folder {folder_name!r} would have {len(unique_include)} chats "
            f"(max {MAX_PER_FOLDER})"
        )

    title = TextWithEntities(text=folder_name, entities=[])
    emoticon = getattr(existing, "emoticon", None) if existing is not None else None
    color = getattr(existing, "color", None) if existing is not None else None

    if isinstance(existing, DialogFilterChatlist):
        new_filter = DialogFilterChatlist(
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
        raise RuntimeError(f"UpdateDialogFilterRequest returned False for {folder_name!r}")


def chunk_matches(
    matches: list[tuple[int, str, object]],
    folder_names: list[str],
    max_per_folder: int,
) -> tuple[list[tuple[str, list[tuple[int, str, object]]]], list[tuple[int, str, object]]]:
    assignments: list[tuple[str, list[tuple[int, str, object]]]] = []
    idx = 0
    for name in folder_names:
        chunk = matches[idx : idx + max_per_folder]
        assignments.append((name, chunk))
        idx += len(chunk)
    overflow = matches[idx:]
    return assignments, overflow


async def run(dry_run: bool, folder_names: list[str]) -> None:
    load_dotenv(ROOT / ".env")
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
        sys.exit(1)

    config = load_config()
    session = str(ROOT / config.session_name)
    client = TelegramClient(session, int(api_id), api_hash, proxy=_proxy_tuple())
    await client.start()

    print("Scanning dialogs for titles containing 'partner' / 'delivery' ...")
    matches = await find_matching_dialogs(client)
    if not matches:
        print("No matching groups found.")
        await client.disconnect()
        return

    print(f"Found {len(matches)} matching group(s)/channel(s).\n")
    capacity = len(folder_names) * MAX_PER_FOLDER
    if len(matches) > capacity:
        print(
            f"WARNING: {len(matches)} chats exceed capacity "
            f"{capacity} ({len(folder_names)} folders × {MAX_PER_FOLDER}). "
            "Overflow will be left out."
        )

    assignments, overflow = chunk_matches(matches, folder_names, MAX_PER_FOLDER)
    for name, chunk in assignments:
        print(f"  {name}: {len(chunk)} chat(s)")
        for chat_id, title, _ in chunk[:5]:
            print(f"    {chat_id:>14}  {title}")
        if len(chunk) > 5:
            print(f"    ... and {len(chunk) - 5} more")
    if overflow:
        print(f"\n  LEFT OUT ({len(overflow)}):")
        for chat_id, title, _ in overflow:
            print(f"    {chat_id:>14}  {title}")

    existing_folders = await list_folders(client)
    print("\nExisting folders:")
    for title, fid, item in existing_folders:
        n = len(getattr(item, "include_peers", []) or [])
        print(f"  id={fid} {title!r} include={n}")

    if dry_run:
        print("\nDry run only. Re-run without --dry-run to apply.")
        await client.disconnect()
        return

    # Refresh folder list after potential creates
    for name, chunk in assignments:
        if not chunk:
            print(f"\nSkipping {name!r}: no chats assigned (Telegram forbids empty folders).")
            continue
        existing_folders = await list_folders(client)
        folder_id, existing = await get_or_create_folder(client, name, existing_folders)
        entities = [e for _, _, e in chunk]
        peers = await build_include_peers(client, entities)
        if not peers:
            print(f"\nSkipping {name!r}: no peers resolved.")
            continue
        print(
            f"\nUpdating {name!r} (id={folder_id}, existing={'yes' if existing else 'new'}) "
            f"with {len(peers)} chat(s)..."
        )
        await update_folder(client, folder_id, name, existing, peers)
        print(f"  OK {name!r}")

    print("\nDone. Open Telegram and check Delivery #1 / #2 / #3.")
    await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list matching groups and planned assignment",
    )
    parser.add_argument(
        "--folders",
        nargs="+",
        default=DEFAULT_FOLDERS,
        help=f"Folder names in fill order (default: {DEFAULT_FOLDERS})",
    )
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, folder_names=list(args.folders)))
