#!/usr/bin/env python3
"""One-shot metrics snapshot for ops (run on server)."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from bot.config_loader import load_config  # noqa: E402
from bot.metrics import (  # noqa: E402
    configure,
    format_report_zh,
    format_stats_zh,
    snapshot,
    write_report_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print management weekly short report instead of full /stats",
    )
    args = parser.parse_args()

    cfg = load_config()
    configure(enabled=cfg.metrics_enabled, state_file=cfg.metrics_state_file)
    snap = snapshot(cfg, include_lark=True)
    if args.report:
        path = write_report_file(snap)
        print(format_report_zh(snap))
        print(f"\n[written] {path}")
    else:
        print(format_stats_zh(snap))


if __name__ == "__main__":
    main()
