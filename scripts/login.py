#!/usr/bin/env python3
"""First-time Telegram login — creates the session file."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

ROOT = Path(__file__).resolve().parent.parent


async def run() -> None:
    load_dotenv(ROOT / ".env")
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    phone = os.getenv("TELEGRAM_PHONE", "").strip()

    if not api_id or not api_hash:
        print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
        sys.exit(1)

    session = str(ROOT / "delivery_session")
    client = TelegramClient(session, int(api_id), api_hash)
    await client.start(phone=phone or None)
    me = await client.get_me()
    print(f"Logged in: {me.first_name} (@{me.username}) id={me.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(run())
