"""Automatic KPI checks for projects that go mainnet-live from 2026-09-30.

First check is 7 days after the live date. Second check is 21 days after it
and is final. Projects that already have a September result post are left
on that earlier review and are not placed on this calendar.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.workflow_form_dispatch import _field_text
from bot.workflow_kpi_result_push import (
    audit_first_check,
    posted_ids,
    send_result_post,
)
from bot.workflow_kpi_write import is_mainnet_live, now_shanghai, parse_live_start

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

SCHEDULE_START = date(2026, 9, 30)
FIRST_DAYS = 7
SECOND_DAYS = 21
RUN_HOUR = 10
_STATE_FILE = ROOT / "data" / "kpi_schedule_state.json"


def runs_on_this_host() -> bool:
    """Only Roy号 posts into Project verification push."""
    return "botchain-qa" in str(ROOT).lower()


def due_round(
    live: datetime,
    today: date,
    *,
    first_done: bool,
    second_done: bool,
) -> str | None:
    """Return the next round that is due, or None."""
    live_day = live.date()
    if live_day < SCHEDULE_START:
        return None
    if second_done:
        return None
    if not first_done and today >= live_day + timedelta(days=FIRST_DAYS):
        return "first"
    if first_done and today >= live_day + timedelta(days=SECOND_DAYS):
        return "second"
    return None


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"first": {}, "second": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"first": {}, "second": {}}
    if not isinstance(raw, dict):
        return {"first": {}, "second": {}}
    first = raw.get("first") if isinstance(raw.get("first"), dict) else {}
    second = raw.get("second") if isinstance(raw.get("second"), dict) else {}
    return {
        "first": {str(k): str(v) for k, v in first.items()},
        "second": {str(k): str(v) for k, v in second.items()},
        "last_run_date": str(raw.get("last_run_date") or ""),
    }


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def select_due(
    records: list[dict[str, Any]],
    *,
    today: date,
    state: dict[str, Any],
    status_field: str,
    name_field: str,
    already_posted: set[str],
) -> list[dict[str, str]]:
    """Projects whose next automatic round is due today or earlier."""
    first_done = state.get("first") or {}
    second_done = state.get("second") or {}
    out: list[dict[str, str]] = []
    for row in records:
        rid = str(row.get("record_id") or "").strip()
        fields = row.get("fields") or {}
        if not rid or not isinstance(fields, dict) or rid in already_posted:
            continue
        if not is_mainnet_live(fields, status_field):
            continue
        live = parse_live_start(fields)
        if live is None:
            continue
        name = _field_text(fields, name_field)
        if not name:
            continue
        round_name = due_round(
            live,
            today,
            first_done=rid in first_done,
            second_done=rid in second_done,
        )
        if not round_name:
            continue
        out.append(
            {
                "record_id": rid,
                "project": name,
                "round": round_name,
                "live_date": live.strftime("%Y-%m-%d"),
            }
        )
    out.sort(key=lambda item: (item["live_date"], item["project"].casefold()))
    return out


def run_due_once(config: AppConfig, *, today: date | None = None) -> dict[str, int]:
    """Audit and post every due round. A failed project is left for the next day."""
    import os

    from bot.lark_bitable import get_tenant_access_token, list_records

    stats = {"due": 0, "sent": 0, "failed": 0}
    if not runs_on_this_host():
        return stats
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("kpi schedule skipped: missing LARK credentials")
        return stats
    token = get_tenant_access_token(app_id, app_secret)
    records = list_records(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
    )
    path = _STATE_FILE
    state = _load_state(path)
    day = today or now_shanghai().date()
    status_field = str(getattr(config, "workflow_status_field", "") or "项目状态")
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
    )
    posted = posted_ids()

    def _send_batch(rows: list[dict[str, Any]], batch: list[dict[str, str]]) -> None:
        for item in batch:
            rid = item["record_id"]
            fields = next(
                (
                    row.get("fields") or {}
                    for row in rows
                    if str(row.get("record_id") or "") == rid
                ),
                {},
            )
            try:
                audited = audit_first_check(
                    token,
                    config,
                    rid,
                    fields,
                    project_name=item["project"],
                    final=item["round"] == "second",
                )
                send_result_post(token, config, audited["markdown"])
            except Exception:
                stats["failed"] += 1
                logger.exception(
                    "kpi schedule failed project=%s round=%s",
                    item["project"],
                    item["round"],
                )
                continue
            state.setdefault(item["round"], {})[rid] = day.isoformat()
            _save_state(path, state)
            stats["sent"] += 1
            logger.info(
                "kpi schedule sent project=%s round=%s valid=%s",
                item["project"],
                item["round"],
                audited.get("valid"),
            )

    due = select_due(
        records,
        today=day,
        state=state,
        status_field=status_field,
        name_field=name_field,
        already_posted=posted,
    )
    stats["due"] = len(due)
    _send_batch(records, due)
    if any(item["round"] == "first" for item in due):
        records = list_records(
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
        )
        state = _load_state(path)
        second = [
            item
            for item in select_due(
                records,
                today=day,
                state=state,
                status_field=status_field,
                name_field=name_field,
                already_posted=posted,
            )
            if item["round"] == "second"
        ]
        stats["due"] += len(second)
        _send_batch(records, second)
    state["last_run_date"] = day.isoformat()
    _save_state(path, state)
    return stats


def _seconds_until_hour(hour: int) -> float:
    now = now_shanghai()
    target = now.replace(hour=hour, minute=0, second=5, microsecond=0)
    if now >= target:
        target = target + timedelta(days=1)
    return max((target - now).total_seconds(), 1.0)


async def kpi_schedule_loop(config: AppConfig) -> None:
    """Run once each Shanghai day at 10:00, and catch up if the process starts later."""
    if not runs_on_this_host():
        return
    logger.info(
        "kpi schedule enabled (first +%d days, second +%d days, daily %02d:00)",
        FIRST_DAYS,
        SECOND_DAYS,
        RUN_HOUR,
    )
    while True:
        now = now_shanghai()
        state = _load_state(_STATE_FILE)
        if state.get("last_run_date") == now.date().isoformat():
            await asyncio.sleep(_seconds_until_hour(RUN_HOUR))
            continue
        if now.hour < RUN_HOUR:
            await asyncio.sleep(_seconds_until_hour(RUN_HOUR))
            continue
        try:
            stats = await asyncio.get_running_loop().run_in_executor(
                None, lambda: run_due_once(config)
            )
            logger.info("kpi schedule cycle %s", stats)
        except Exception:
            logger.exception("kpi schedule cycle failed")
        await asyncio.sleep(_seconds_until_hour(RUN_HOUR))
