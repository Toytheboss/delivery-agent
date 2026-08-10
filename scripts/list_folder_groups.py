#!/usr/bin/env python3
"""List groups in the configured Delivery Telegram folder."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config_loader import load_config
from bot.folder_scope import fetch_folder_chat_ids


async def run() -> None:
    load_dotenv(ROOT / ".env")
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
        sys.exit(1)

    config = load_config()
    session = str(ROOT / config.session_name)
    client = TelegramClient(session, int(api_id), api_hash)
    await client.start()

    chat_ids = await fetch_folder_chat_ids(client, config.folder_names)
    if not chat_ids:
        print(f"No chats in folders {config.folder_names!r}")
        await client.disconnect()
        return

    print(f"Folders {config.folder_names!r} — {len(chat_ids)} chat(s):\n")
    for cid in sorted(chat_ids):
        try:
            entity = await client.get_entity(cid)
            title = getattr(entity, "title", None) or getattr(entity, "first_name", "?")
            print(f"  chat_id={cid}  title={title!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  chat_id={cid}  (could not resolve: {exc})")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
