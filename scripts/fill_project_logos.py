#!/usr/bin/env python3
"""Manual backfill: missing 项目logo via site header / browser (uses bot.project_logo)."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.lark_bitable import get_tenant_access_token, list_records  # noqa: E402
from bot.project_logo import fill_logo_for_record, pick_site_url  # noqa: E402
from bot.workflow_form_dispatch import _field_text  # noqa: E402

load_dotenv(ROOT / ".env")

BASE = "Kb6rbLenJa4FzWsi6pzlTkdjg0e"
TABLE = "tbl5wXOwCptng06w"
NAME = "项目名称 Project Name"
LOGO = "项目logo"
LIVE_LINK = "已上线链接🔗"
PROJ_LINK = "项目链接"
LIVE_STATUS = "Mainnet Live"


def log(msg: str) -> None:
    print(msg, flush=True)


def process_one(token: str, rid: str, name: str, site: str) -> tuple[str, str]:
    try:
        status = fill_logo_for_record(token, BASE, TABLE, rid, name, site, LOGO)
    except Exception as exc:  # noqa: BLE001
        return name, f"err:{exc}"
    return name, status


def main() -> int:
    live_only = "--live-only" in sys.argv
    workers = 3
    token = get_tenant_access_token(os.environ["LARK_APP_ID"], os.environ["LARK_APP_SECRET"])
    log("listing records…")
    records = list_records(token, BASE, TABLE)
    log(f"loaded {len(records)} records")

    targets: list[tuple[str, str, str]] = []
    for rec in records:
        fields = rec.get("fields") or {}
        if fields.get(LOGO):
            continue
        status = _field_text(fields, "项目状态")
        if live_only and status != LIVE_STATUS:
            continue
        site = pick_site_url(fields, LIVE_LINK, PROJ_LINK)
        if not site:
            continue
        rid = str(rec.get("record_id") or "")
        name = _field_text(fields, NAME) or rid
        targets.append((rid, name, site))

    targets.sort(key=lambda x: x[1].lower())
    log(f"targets: {len(targets)} (workers={workers})")

    ok = fail = 0
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(process_one, token, rid, name, site): (name, site)
            for rid, name, site in targets
        }
        for i, fut in enumerate(as_completed(futs), 1):
            name, site = futs[fut]
            try:
                n, status = fut.result()
            except Exception as exc:  # noqa: BLE001
                n, status = name, f"err:{exc}"
            if status.startswith("ok"):
                ok += 1
                log(f"[{i}/{len(targets)}] OK {n} ({status})")
            else:
                fail += 1
                failures.append(f"{n}: {status} ({site})")
                log(f"[{i}/{len(targets)}] FAIL {n}: {status}")

    log("\n=== SUMMARY ===")
    log(f"ok={ok} fail={fail} total={len(targets)}")
    if failures:
        log("failures:")
        for line in failures:
            log(f"  {line}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
