#!/usr/bin/env python3
"""Move folder chats whose last message is on or before a date out of folders.

Does not leave the groups. Reads scope.inactive_before (UTC+8).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, utils
from telethon.tl.functions.messages import UpdateDialogFilterRequest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config_loader import load_config
from bot.folder_auto_add import (
    _folder_peer_ids,
    _write_folder,
    discover_project_folders,
    inactive_on_or_before,
)


async def run(*, apply: bool, session_path: str) -> None:
    load_dotenv(ROOT / ".env")
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
        sys.exit(1)
    config = load_config()
    cutoff = str(getattr(config, "folder_inactive_before", "") or "").strip()
    if not cutoff:
        print("scope.inactive_before is empty")
        sys.exit(1)

    session = session_path or str(ROOT / config.session_name)
    client = TelegramClient(session, int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("session is not authorized")
        await client.disconnect()
        sys.exit(1)

    dates: dict[int, object] = {}
    titles: dict[int, str] = {}
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if entity is None:
            continue
        try:
            peer_id = int(utils.get_peer_id(entity))
        except Exception:
            continue
        dates[peer_id] = dialog.date
        titles[peer_id] = str(getattr(entity, "title", None) or "")

    folders = await discover_project_folders(
        client,
        configured_names=list(config.folder_names or []),
        prefix=(config.folder_name_prefix or "botchain"),
    )
    remove_ids: set[int] = set()
    unknown = 0
    kept = 0
    per_folder: list[tuple[str, int, int]] = []

    for name, fid, item in folders:
        ids, pinned, include = await _folder_peer_ids(client, item)
        drop: set[int] = set()
        stay_pinned = []
        stay_include = []
        for peer in pinned:
            try:
                peer_id = int(utils.get_peer_id(peer))
            except Exception:
                stay_pinned.append(peer)
                unknown += 1
                continue
            when = dates.get(peer_id)
            if peer_id not in dates:
                stay_pinned.append(peer)
                unknown += 1
                continue
            if inactive_on_or_before(when, cutoff):
                drop.add(peer_id)
            else:
                stay_pinned.append(peer)
        for peer in include:
            try:
                peer_id = int(utils.get_peer_id(peer))
            except Exception:
                stay_include.append(peer)
                unknown += 1
                continue
            if peer_id in drop:
                continue
            when = dates.get(peer_id)
            if peer_id not in dates:
                stay_include.append(peer)
                unknown += 1
                continue
            if inactive_on_or_before(when, cutoff):
                drop.add(peer_id)
            else:
                stay_include.append(peer)
        remove_ids |= drop
        kept += len(ids) - len(drop)
        per_folder.append((name, len(ids), len(drop)))
        print(f"{name}: {len(ids)} in folder, {len(drop)} to remove")
        if not apply:
            continue
        if not drop:
            continue
        if not stay_pinned and not stay_include:
            ok = await client(UpdateDialogFilterRequest(id=fid, filter=None))
            print(f"  deleted empty folder {name!r} ok={ok}")
        else:
            await _write_folder(
                client,
                folder_id=fid,
                folder_name=name,
                existing=item,
                pinned_peers=stay_pinned,
                include_peers=stay_include,
            )
            print(f"  updated {name!r} now {len(stay_pinned) + len(stay_include)}")
        await asyncio.sleep(1)

    print(
        f"cutoff={cutoff} folders={len(folders)} "
        f"remove={len(remove_ids)} keep={kept} unknown={unknown} apply={apply}"
    )
    await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--session", default="")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply, session_path=args.session))
