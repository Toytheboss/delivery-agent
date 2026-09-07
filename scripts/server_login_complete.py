#!/usr/bin/env python3
"""Complete Telethon login with verification code (and optional 2FA password).

Usage:
  .venv/bin/python scripts/server_login_complete.py <CODE> [2FA_PASSWORD]
"""

from __future__ import annotations

import asyncio
import getpass
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

ROOT = Path(__file__).resolve().parent.parent
SESSION = ROOT / "delivery_session"
STATE_PATH = ROOT / "data" / "login_pending.json"


async def run(code: str, password: str | None) -> int:
    load_dotenv(ROOT / ".env")
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    phone = os.getenv("TELEGRAM_PHONE", "").strip()
    phone_code_hash = ""

    if STATE_PATH.is_file():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        phone = state.get("phone") or phone
        phone_code_hash = state.get("phone_code_hash") or ""

    if not api_id or not api_hash or not phone:
        print("ERROR: missing TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_PHONE")
        return 1
    if not phone_code_hash:
        print("ERROR: missing phone_code_hash — run server_login_request_code.py first")
        return 1

    client = TelegramClient(str(SESSION), int(api_id), api_hash)
    await client.connect()

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        if not password:
            password = getpass.getpass("Telegram 2FA password: ")
        try:
            await client.sign_in(password=password)
        except PasswordHashInvalidError:
            print("ERROR: invalid 2FA password")
            await client.disconnect()
            return 1
    except PhoneCodeInvalidError:
        print("ERROR: invalid verification code")
        await client.disconnect()
        return 1
    except PhoneCodeExpiredError:
        print("ERROR: code expired — run server_login_request_code.py again")
        await client.disconnect()
        return 1

    me = await client.get_me()
    print(f"LOGGED_IN=1 name={me.first_name} username=@{getattr(me, 'username', None)} id={me.id}")
    if STATE_PATH.is_file():
        STATE_PATH.unlink()
    await client.disconnect()
    return 0


if __name__ == "__main__":
    code = sys.argv[1].strip() if len(sys.argv) > 1 else input("Telegram verification code: ").strip()
    pw = sys.argv[2] if len(sys.argv) > 2 else None
    raise SystemExit(asyncio.run(run(code, pw)))
