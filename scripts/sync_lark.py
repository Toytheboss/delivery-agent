#!/usr/bin/env python3
"""Sync Lark Wiki content into knowledge/ for RAG retrieval."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.lark_sync import sync_lark_wiki  # noqa: E402


def main() -> int:
    import os

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    wiki_token = os.getenv("LARK_WIKI_TOKEN", "").strip()

    if not app_id or not app_secret or not wiki_token:
        print("Set LARK_APP_ID, LARK_APP_SECRET, LARK_WIKI_TOKEN in .env")
        return 1

    out_dir = ROOT / "knowledge"

    try:
        sync_lark_wiki(out_dir, app_id, app_secret, wiki_token)
    except Exception as exc:  # noqa: BLE001
        print(f"Sync failed: {exc}")
        return 1

    out_file = out_dir / f"lark_{wiki_token}.md"
    print(f"Synced to {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
