"""Automatic KPI checks for projects that go mainnet-live from 2026-09-30.

Until 2026-10-15 19:00 Shanghai the first check is 7 days after the live
date and the second check is 21 days after it. After that moment the first
check is 3 days after the live date and the second check is 14 days later.
Projects that already have a September result post are left on that earlier
review and are not placed on this calendar.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.workflow_form_dispatch import _field_text
from bot.workflow_kpi_result_push import (
    audit_first_check,
    log_review_posted,
    posted_ids,
    send_result_post,
)
from bot.workflow_kpi_write import (
    CADENCE_CHANGE_AT,
    field_result,
    is_mainnet_live,
    now_shanghai,
    parse_live_start,
    review_offsets,
)

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

SCHEDULE_START = date(2026, 9, 30)
RUN_HOUR = 10
_COORD_FIELD = "KPI Final"
_HELD_COORD = "暂扣整改"
_STATE_FILE = ROOT / "data" / "kpi_schedule_state.json"


def runs_on_this_host() -> bool:
    """Only 审核号 posts into Project verification push."""
    return "botchain-qa" in str(ROOT).lower()


def due_round(
    live: datetime,
    today: date,
    *,
    first_done: bool,
    second_done: bool,
    at: datetime | None = None,
) -> str | None:
    """Return the next round that is due, or None."""
    live_day = live.date()
    if live_day < SCHEDULE_START:
        return None
    if second_done:
        return None
    first_days, second_days = review_offsets(at)
    if not first_done and today >= live_day + timedelta(days=first_days):
        return "first"
    if first_done and today >= live_day + timedelta(days=second_days):
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
        "september_final_done": bool(raw.get("september_final_done")),
    }


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mark_rounds_done(
    record_id: str,
    *,
    rounds: tuple[str, ...] = ("first", "second"),
    day: date | None = None,
    path: Path | None = None,
) -> None:
    """Record that automatic rounds are finished so the daily scan skips them."""
    rid = (record_id or "").strip()
    if not rid:
        return
    stamp = (day or now_shanghai().date()).isoformat()
    file = path or _STATE_FILE
    state = _load_state(file)
    for round_name in rounds:
        key = str(round_name or "").strip()
        if key not in {"first", "second"}:
            continue
        bucket = state.setdefault(key, {})
        # Keep the original first-check day (e.g. 2026-09-30 batch). Early
        # final must not overwrite it with today's date.
        if key == "first" and str(bucket.get(rid) or "").strip():
            continue
        bucket[rid] = stamp
    _save_state(file, state)


def first_check_date_for(record_id: str, path: Path | None = None) -> str:
    rid = (record_id or "").strip()
    if not rid:
        return ""
    state = _load_state(path or _STATE_FILE)
    return str((state.get("first") or {}).get(rid) or "").strip()


def select_due(
    records: list[dict[str, Any]],
    *,
    today: date,
    state: dict[str, Any],
    status_field: str,
    name_field: str,
    already_posted: set[str],
    at: datetime | None = None,
) -> list[dict[str, str]]:
    """Projects whose next automatic round is due today or earlier.

    Calendar second checks only run while KPI Final is still 暂扣整改.
    通过 / 有效 KPI / 不通过 are already closed and are skipped.
    """
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
            at=at,
        )
        if not round_name:
            continue
        if round_name == "second" and field_result(fields, _COORD_FIELD) != _HELD_COORD:
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
    moment = now_shanghai()
    day = today or moment.date()
    if today is not None:
        moment = datetime(
            today.year, today.month, today.day, 12, 0, tzinfo=moment.tzinfo
        )
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
                is_second = item["round"] == "second"
                audited = audit_first_check(
                    token,
                    config,
                    rid,
                    fields,
                    project_name=item["project"],
                    final=is_second,
                    final_trigger="calendar",
                    first_check_date=first_check_date_for(rid, path) if is_second else "",
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
            log_review_posted(
                project_name=item["project"],
                record_id=rid,
                final=is_second,
                result=str(audited.get("result") or ""),
            )

    due = select_due(
        records,
        today=day,
        state=state,
        status_field=status_field,
        name_field=name_field,
        already_posted=posted,
        at=moment,
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
                at=moment,
            )
            if item["round"] == "second"
        ]
        stats["due"] += len(second)
        _send_batch(records, second)
    state["last_run_date"] = day.isoformat()
    _save_state(path, state)
    return stats


def select_september_held(
    records: list[dict[str, Any]],
    *,
    state: dict[str, Any],
    status_field: str,
    name_field: str,
) -> list[dict[str, str]]:
    """September 2026 mainnet-live rows still held. Already-final rows are skipped."""
    second_done = state.get("second") or {}
    out: list[dict[str, str]] = []
    for row in records:
        rid = str(row.get("record_id") or "").strip()
        fields = row.get("fields") or {}
        if not rid or not isinstance(fields, dict) or rid in second_done:
            continue
        if not is_mainnet_live(fields, status_field):
            continue
        live = parse_live_start(fields)
        if live is None or live.year != 2026 or live.month != 9:
            continue
        if field_result(fields, _COORD_FIELD) != _HELD_COORD:
            continue
        name = _field_text(fields, name_field)
        if not name:
            continue
        out.append(
            {
                "record_id": rid,
                "project": name,
                "round": "second",
                "live_date": live.strftime("%Y-%m-%d"),
            }
        )
    out.sort(key=lambda item: (item["live_date"], item["project"].casefold()))
    return out


def run_september_final_once(config: AppConfig) -> dict[str, int]:
    """Final-check every September held project once, at or after the cutover."""
    import os

    from bot.lark_bitable import get_tenant_access_token, list_records

    stats = {"due": 0, "sent": 0, "failed": 0}
    if not runs_on_this_host():
        return stats
    path = _STATE_FILE
    state = _load_state(path)
    if state.get("september_final_done"):
        return stats
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("september final skipped: missing LARK credentials")
        return stats
    token = get_tenant_access_token(app_id, app_secret)
    records = list_records(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
    )
    status_field = str(getattr(config, "workflow_status_field", "") or "项目状态")
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
    )
    due = select_september_held(
        records,
        state=state,
        status_field=status_field,
        name_field=name_field,
    )
    stats["due"] = len(due)
    day = now_shanghai().date()
    for item in due:
        rid = item["record_id"]
        fields = next(
            (
                row.get("fields") or {}
                for row in records
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
                final=True,
                final_trigger="batch",
                first_check_date=first_check_date_for(rid, path),
            )
            send_result_post(token, config, audited["markdown"])
        except Exception:
            stats["failed"] += 1
            logger.exception(
                "september final failed project=%s",
                item["project"],
            )
            continue
        mark_rounds_done(
            rid, rounds=("first", "second"), day=day, path=path
        )
        stats["sent"] += 1
        logger.info(
            "september final sent project=%s valid=%s",
            item["project"],
            audited.get("valid"),
        )
        log_review_posted(
            project_name=item["project"],
            record_id=rid,
            final=True,
            result=str(audited.get("result") or ""),
        )
    if stats["failed"] == 0:
        state = _load_state(path)
        state["september_final_done"] = True
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
    first_days, second_days = review_offsets()
    logger.info(
        "kpi schedule enabled (first +%d days, second +%d days, daily %02d:00)",
        first_days,
        second_days,
        RUN_HOUR,
    )
    while True:
        now = now_shanghai()
        state = _load_state(_STATE_FILE)
        if not state.get("september_final_done") and now >= CADENCE_CHANGE_AT:
            try:
                stats = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: run_september_final_once(config)
                )
                logger.info("september final cycle %s", stats)
            except Exception:
                logger.exception("september final cycle failed")
            state = _load_state(_STATE_FILE)
            if not state.get("september_final_done"):
                await asyncio.sleep(300)
                continue
        now = now_shanghai()
        state = _load_state(_STATE_FILE)
        if (
            state.get("last_run_date") != now.date().isoformat()
            and now.hour >= RUN_HOUR
        ):
            try:
                stats = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: run_due_once(config)
                )
                logger.info("kpi schedule cycle %s", stats)
            except Exception:
                logger.exception("kpi schedule cycle failed")
        now = now_shanghai()
        state = _load_state(_STATE_FILE)
        waits = [_seconds_until_hour(RUN_HOUR)]
        if not state.get("september_final_done") and now < CADENCE_CHANGE_AT:
            waits.append(max((CADENCE_CHANGE_AT - now).total_seconds(), 1.0))
        await asyncio.sleep(max(min(waits), 1.0))
