#!/usr/bin/env python3
"""Synchronize Progress Tracker KPI 2 results from its PR-link cell.

The criterion is deliberately mechanical:
  - a non-empty ``KPI 2 - PR 新闻链接验证`` cell → 新闻验证结果 = 通过
  - an empty cell → 新闻验证结果 = 不通过

This script is intentionally manual (dry-run by default). It does not create a
Day-based audit schedule, write KPI coordination fields, or send group pushes.
Use ``--execute`` only after reviewing its plan.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.lark_bitable import get_tenant_access_token, list_records, update_record  # noqa: E402
from bot.workflow_form_chase import field_is_filled  # noqa: E402
from bot.workflow_form_dispatch import _field_text  # noqa: E402

DEFAULT_APP_TOKEN = "Kb6rbLenJa4FzWsi6pzlTkdjg0e"
DEFAULT_TABLE_ID = "tbl5wXOwCptng06w"
DEFAULT_LINK_FIELD = "KPI 2 - PR 新闻链接验证"
DEFAULT_RESULT_FIELD = "新闻验证结果"
PASS = "通过"
FAIL = "不通过"


def expected_result(fields: dict[str, Any], link_field: str) -> str:
    """Return KPI 2's result from whether its link cell has usable content."""
    return PASS if field_is_filled(fields, link_field) else FAIL


def selected_value(value: Any) -> str:
    """Read a Lark single-select value in its common API representations."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and value:
        return selected_value(value[0])
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "").strip()
    return ""


def plan_updates(
    records: list[dict[str, Any]],
    *,
    link_field: str,
    result_field: str,
) -> list[dict[str, str]]:
    """Return only tracker rows whose KPI 2 result differs from its link state."""
    plan: list[dict[str, str]] = []
    for record in records:
        record_id = str(record.get("record_id") or "").strip()
        fields = record.get("fields") or {}
        if not record_id:
            continue
        wanted = expected_result(fields, link_field)
        current = selected_value(fields.get(result_field))
        if current == wanted:
            continue
        plan.append(
            {
                "record_id": record_id,
                "project": _field_text(fields, "项目名称 Project Name")
                or _field_text(fields, "Project name")
                or "(unnamed project)",
                "link": _field_text(fields, link_field),
                "current": current or "(empty)",
                "wanted": wanted,
            }
        )
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-token", default=DEFAULT_APP_TOKEN)
    parser.add_argument("--table-id", default=DEFAULT_TABLE_ID)
    parser.add_argument("--link-field", default=DEFAULT_LINK_FIELD)
    parser.add_argument("--result-field", default=DEFAULT_RESULT_FIELD)
    parser.add_argument("--limit", type=int, default=0, help="Maximum writes; 0 is unlimited.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply updates. Without this flag the script only prints a plan.",
    )
    return parser.parse_args()


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    args = parse_args()
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("ERROR: LARK_APP_ID and LARK_APP_SECRET must be set.", file=sys.stderr)
        return 2

    token = get_tenant_access_token(app_id, app_secret)
    records = list_records(token, args.app_token, args.table_id)
    plan = plan_updates(
        records,
        link_field=args.link_field,
        result_field=args.result_field,
    )

    pass_count = sum(item["wanted"] == PASS for item in plan)
    fail_count = len(plan) - pass_count
    print(f"Scanned records: {len(records)}")
    print(f"Would update: {len(plan)} (pass={pass_count}, fail={fail_count})")
    for item in plan:
        link = item["link"] or "(empty)"
        print(
            f"  {item['project']} [{item['record_id']}]: "
            f"{item['current']} -> {item['wanted']} | {link}"
        )

    if not args.execute:
        print("DRY-RUN only. Re-run with --execute to write the planned results.")
        return 0

    limit = args.limit if args.limit > 0 else len(plan)
    updated = 0
    for item in plan[:limit]:
        update_record(
            token,
            args.app_token,
            args.table_id,
            item["record_id"],
            {args.result_field: [item["wanted"]]},
        )
        updated += 1
        print(f"UPDATED {item['project']} -> {item['wanted']}")
    print(f"Updated: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
