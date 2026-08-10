#!/usr/bin/env python3
"""Upsert integration-blockers FAQ entries into Lark Agent KB (no full wipe)."""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.agent_kb_sync import (  # noqa: E402
    AgentKbEntry,
    ensure_agent_kb_fields,
    upsert_entry_to_lark,
)
from bot.lark_bitable import get_tenant_access_token, list_records  # noqa: E402

DEFAULT_APP = "Kb6rbLenJa4FzWsi6pzlTkdjg0e"
DEFAULT_TABLE = "tblP28CyWdY5ml8r"
SRC = ROOT / "knowledge" / "delivery_integration_blockers_faq_zh_en.md"

FIELD_RE = re.compile(
    r"【(相关问题|关键词|参考回答(?:-中文|-英文)?|来源)】\s*(.*?)(?=\n【|\Z)",
    re.DOTALL,
)


def _parse() -> list[AgentKbEntry]:
    text = SRC.read_text(encoding="utf-8")
    parts = re.split(r"(?=【相关问题】)", text)
    now = datetime.now().isoformat(timespec="seconds")
    out: list[AgentKbEntry] = []
    n = 0
    for part in parts:
        if "【相关问题】" not in part:
            continue
        fields = {
            m.group(1): m.group(2).strip()
            for m in FIELD_RE.finditer(part)
        }
        raw_q = (fields.get("相关问题") or "").strip()
        # ZH / EN separator is " / " before an English sentence (capital letter).
        # Do not split on "swap / LP" style inners.
        parts_q = re.split(r"\s+/\s+(?=[A-Z\"'])", raw_q, maxsplit=1)
        q = (parts_q[1] if len(parts_q) == 2 else parts_q[0]).strip()
        zh = (fields.get("参考回答-中文") or "").strip()
        en = (fields.get("参考回答-英文") or "").strip()
        if not q or (not zh and not en):
            continue
        answer = f"{zh}\n\n[EN]\n{en}" if zh and en else (zh or en)
        n += 1
        out.append(
            AgentKbEntry(
                entry_id=f"INTG-BLOCK-{n:03d}",
                category="Integration / 对接答疑",
                question=q,
                answer=answer,
                keywords=fields.get("关键词", ""),
                source=(fields.get("来源") or SRC.name).splitlines()[0].strip(),
                updated_at=now,
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--app-token", default=DEFAULT_APP)
    parser.add_argument("--table-id", default=DEFAULT_TABLE)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    entries = _parse()
    print(f"Parsed {len(entries)} entries from {SRC.name}")
    for e in entries:
        print(f"  {e.entry_id}: {e.question[:70]}")
    if args.dry_run:
        return 0

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("Missing LARK_APP_ID / LARK_APP_SECRET")
        return 1

    token = get_tenant_access_token(app_id, app_secret)
    ensure_agent_kb_fields(token, args.app_token, args.table_id)
    existing = list_records(token, args.app_token, args.table_id)
    id_map = {}
    for rec in existing:
        rid = str(rec.get("record_id") or rec.get("id") or "")
        fields = rec.get("fields") or {}
        eid = str(fields.get("编号") or "").strip()
        if rid and eid:
            id_map[eid] = rid

    for e in entries:
        rid, action = upsert_entry_to_lark(
            e,
            app_id=app_id,
            app_secret=app_secret,
            app_token=args.app_token,
            table_id=args.table_id,
            existing_ids=id_map,
        )
        print(f"{action}: {e.entry_id} -> {rid}")
        if rid:
            id_map[e.entry_id] = rid
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
