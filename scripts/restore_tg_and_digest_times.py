#!/usr/bin/env python3
"""Restore TG/QA on project events; give wallet digest rows a real timestamp."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

DASH = Path("/opt/josh-dashboard/bot/dashboard_snapshot.py")
JSONL = Path("/opt/botchain-qa-tg-bot/data/workflow_events.jsonl")
STATE = Path("/opt/botchain-qa-tg-bot/data/lark_wallet_digest_state.json")

OLD_SLICE = '"project_events": _delivery_automation_events(unique_events),\n'
NEW_SLICE = '"project_events": unique_events,\n'

OLD_DIGEST = """            if digest_completed:
                project_events.append(
                    {
                        "kind": "wallet_digest_completed",
                        "text": (
                            f"{name} 的钱包地址已纳入午夜日报"
                            + ("" if digest_event else "（历史状态无时间）")
                        ),
                        "ts": str((digest_event or {}).get("ts") or ""),
                        "source": "Lark 钱包地址日报",
                        "status": "success",
                    }
                )
"""

NEW_DIGEST = """            digest_ts = str((digest_event or {}).get("ts") or "")
            if digest_completed and not digest_ts and digest_date:
                try:
                    send_day = datetime.strptime(str(digest_date)[:10], "%Y-%m-%d")
                    send_day = send_day + timedelta(days=1)
                    digest_ts = send_day.strftime("%Y-%m-%dT00:00:02+08:00")
                except ValueError:
                    digest_ts = ""
            if digest_completed:
                project_events.append(
                    {
                        "kind": "wallet_digest_completed",
                        "text": f"{name} 的钱包地址已纳入午夜日报",
                        "ts": digest_ts,
                        "source": "Lark 钱包地址日报",
                        "status": "success",
                    }
                )
"""


def midnight_digest_sent_ts(digest_date: str) -> str:
    day = datetime.strptime(str(digest_date)[:10], "%Y-%m-%d") + timedelta(days=1)
    return f"{day.strftime('%Y-%m-%d')}T00:00:02+08:00"


def patch_dashboard() -> None:
    text = DASH.read_text(encoding="utf-8")
    if OLD_SLICE in text:
        text = text.replace(OLD_SLICE, NEW_SLICE, 1)
        print("restored unique_events (TG/QA included)")
    elif '"project_events": unique_events,' in text:
        print("slice already unique_events")
    else:
        raise SystemExit("project_events slice not found")
    if OLD_DIGEST in text:
        text = text.replace(OLD_DIGEST, NEW_DIGEST, 1)
        print("patched digest timestamp fallback")
    elif 'text": f"{name} 的钱包地址已纳入午夜日报"' in text and "历史状态无时间" not in text:
        print("digest block already patched")
    else:
        raise SystemExit("digest block not found")
    DASH.write_text(text, encoding="utf-8")


def backfill_digest_jsonl() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    last = str(state.get("last_digest_date") or "")
    counts = Counter(
        str(v)
        for v in (state.get("first_seen") or {}).values()
        if str(v) not in {"", "baseline"}
    )
    existing = JSONL.read_text(encoding="utf-8")
    have = set()
    for line in existing.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") == "wallet_digest_sent":
            have.add(str(row.get("digest_date") or ""))
    added = 0
    with JSONL.open("a", encoding="utf-8") as fh:
        for day, n in sorted(counts.items()):
            if day > last or day in have:
                continue
            ts = midnight_digest_sent_ts(day)
            send_day = ts[:10]
            ev = {
                "ts": ts,
                "day": send_day,
                "kind": "wallet_digest_sent",
                "source": "lark_wallet_digest",
                "project_name": "",
                "text": f"钱包日报已发送（{day}，{n} 个项目）",
                "status": "success",
                "digest_date": day,
                "project_count": n,
                "event_id": f"wallet-digest-{day}",
            }
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            added += 1
            print("jsonl+", day, "projects", n, "ts", ts)
    print("backfilled", added)


if __name__ == "__main__":
    patch_dashboard()
    backfill_digest_jsonl()
    print("ok")
