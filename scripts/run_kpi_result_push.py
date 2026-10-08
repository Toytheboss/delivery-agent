#!/usr/bin/env python3
"""List or send September first-check result posts.

Without --send this only prints pending projects. It does not audit or post.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from bot.config_loader import load_config  # noqa: E402
from bot.lark_bitable import get_tenant_access_token, list_records  # noqa: E402
from bot.workflow_kpi_result_push import (  # noqa: E402
    push_pending,
    run_early_final_after_submit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send",
        action="store_true",
        help="Audit pending September projects and post the English result",
    )
    parser.add_argument(
        "--early-final",
        action="store_true",
        help="Run submit-triggered final review for --project and print JSON",
    )
    parser.add_argument("--project", default="", help="Limit to one project name")
    parser.add_argument("--record-id", default="", help="Progress-table record id")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = load_config()
    if args.early_final:
        if not str(args.project or "").strip():
            raise SystemExit("need --project")
        out = run_early_final_after_submit(
            config,
            project_name=str(args.project).strip(),
            record_id=str(args.record_id or "").strip(),
        )
        print(json.dumps(out, ensure_ascii=False, default=str))
        return
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise SystemExit("Missing LARK_APP_ID / LARK_APP_SECRET")
    token = get_tenant_access_token(app_id, app_secret)
    records = list_records(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
    )
    rows = push_pending(
        token,
        config,
        records,
        send=bool(args.send),
        project_name=args.project,
    )
    if not args.send:
        for row in rows:
            print(f"pending {row['project']} {row['record_id']}")
        print(f"{len(rows)} pending. Pass --send to audit and post.")
        return
    for row in rows:
        if row.get("sent"):
            label = "valid" if row.get("valid") else "held"
            print(f"sent {row['project']} {label}")
        else:
            print(f"failed {row['project']}: {row.get('error')}")


if __name__ == "__main__":
    main()
