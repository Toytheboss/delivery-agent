#!/usr/bin/env python3
"""Retry logo fill for live progress rows still missing 项目logo（文件）."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from bot.config_loader import load_config
from bot.lark_bitable import get_tenant_access_token, list_records
from bot.project_logo import fill_logo_for_record, pick_site_url
from bot.workflow_form_chase import field_is_filled
from bot.workflow_form_dispatch import _field_text
from bot.workflow_logo_fill import _load_state, _save_state


def main() -> int:
    cfg = load_config()
    token = get_tenant_access_token(
        os.environ["LARK_APP_ID"].strip(), os.environ["LARK_APP_SECRET"].strip()
    )
    rows = list_records(
        token, cfg.workflow_base_app_token, cfg.workflow_progress_table_id
    )
    live = cfg.workflow_trigger_status
    logo_field = cfg.workflow_logo_field
    state_path = ROOT / cfg.workflow_logo_state_file
    processed, results = _load_state(state_path)

    missing = []
    for rec in rows:
        fields = rec.get("fields") or {}
        if _field_text(fields, cfg.workflow_status_field) != live:
            continue
        rid = str(rec.get("record_id") or "")
        if not rid:
            continue
        if field_is_filled(fields, logo_field):
            continue
        name = _field_text(fields, cfg.workflow_project_name_field) or rid
        site = pick_site_url(
            fields, cfg.workflow_live_link_field, cfg.workflow_project_link_field
        )
        missing.append((rid, name, site))

    todo = [(rid, name, site) for rid, name, site in missing if site]
    print(
        json.dumps(
            {
                "missing": len(missing),
                "retry": len(todo),
                "no_url": len(missing) - len(todo),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    ok = fail = 0
    details = []
    for i, (rid, name, site) in enumerate(todo, 1):
        t0 = time.time()
        try:
            status = fill_logo_for_record(
                token,
                cfg.workflow_base_app_token,
                cfg.workflow_progress_table_id,
                rid,
                name,
                site,
                logo_field,
            )
        except Exception as exc:  # noqa: BLE001
            status = f"err:{exc}"
        elapsed = round(time.time() - t0, 1)
        processed.add(rid)
        results[rid] = f"retry:{status}"
        row = {
            "i": i,
            "n": len(todo),
            "name": name,
            "record_id": rid,
            "site": site,
            "status": status,
            "sec": elapsed,
        }
        details.append(row)
        if str(status).startswith("ok"):
            ok += 1
        else:
            fail += 1
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if i % 10 == 0:
            _save_state(state_path, processed, results)

    _save_state(state_path, processed, results)
    summary = {"ok": ok, "fail": fail, "retried": len(todo)}
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    out = ROOT / "data" / "logo_retry_live_missing.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"summary": summary, "details": details}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
