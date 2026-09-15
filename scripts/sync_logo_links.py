#!/usr/bin/env python3
"""One-shot: wallet「Project logo」→ progress「项目logo （链接）」when empty."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config_loader import load_config
from bot.workflow_logo_link_sync import sync_logo_links_once


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    os.chdir(ROOT)
    cfg = load_config()
    stats = sync_logo_links_once(cfg, dry_run=args.dry_run, limit=args.limit)
    print(stats)
    return 0 if stats.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
