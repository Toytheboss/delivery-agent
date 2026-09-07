#!/usr/bin/env python3
"""One-shot: request Telegram login code and persist partial session.

Usage on server:
  cd /opt/delivery-agent && .venv/bin/python scripts/server_login_request_code.py

Then complete with:
  .venv/bin/python scripts/server_login_complete.py <CODE> [password]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError, PhoneNumberInvalidError

ROOT = Path(__file__).resolve().parent.parent
SESSION = ROOT / "delivery_session"
STATE_PATH = ROOT / "data" / "login_pending.json"


def _mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit() or c == "+")
    if len(digits) <= 4:
        return "****"
    return f"{digits[:3]}****{digits[-2:]}"


async def run() -> int:
    load_dotenv(ROOT / ".env")
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    phone = os.getenv("TELEGRAM_PHONE", "").strip()

    if not api_id or not api_hash:
        print("ERROR: Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
        return 1
    if not phone:
        print("ERROR: Set TELEGRAM_PHONE in .env (E.164, e.g. +86138...)")
        return 1

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(str(SESSION), int(api_id), api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(
            f"ALREADY_AUTHORIZED: {me.first_name} "
            f"(@{getattr(me, 'username', None)}) id={me.id}"
        )
        await client.disconnect()
        return 0

    print(f"Requesting login code for phone={_mask_phone(phone)} ...")
    try:
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        print("ERROR: PhoneNumberInvalidError — check TELEGRAM_PHONE format")
        await client.disconnect()
        return 1
    except FloodWaitError as e:
        print(f"ERROR: FloodWaitError — wait {e.seconds}s before retry")
        await client.disconnect()
        return 1

    phone_code_hash = getattr(sent, "phone_code_hash", "") or ""
    state = {
        "phone": phone,
        "phone_masked": _mask_phone(phone),
        "phone_code_hash": phone_code_hash,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "session": str(SESSION),
        "type": type(sent).__name__,
    }
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # Ensure SQLite session is flushed
    await client.disconnect()

    print("CODE_SENT=1")
    print(f"PHONE_MASKED={_mask_phone(phone)}")
    print(f"PHONE_CODE_HASH_PREFIX={phone_code_hash[:8]}..." if phone_code_hash else "PHONE_CODE_HASH=")
    print(f"STATE_FILE={STATE_PATH}")
    print(f"SESSION_FILE={SESSION}.session")
    print("NEXT: enter the Telegram verification code via server_login_complete.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
