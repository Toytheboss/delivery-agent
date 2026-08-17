"""Daily 22:00 Lark digest: new wallet rows today → project count + address count."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.lark_im import send_text_to_chat
from bot.workflow_form_dispatch import _field_text
from bot.workflow_events import append_event

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_EVENTS_FILE = "data/workflow_events.jsonl"

ADDRESS_FIELDS = [
    "Contract Addresss/主网合约",
    "Treasury Address",
    "Fee Collector / Revenue Wallet Address",
    "Grant Receiving Wallet (Optional)",
    "MM / LP Wallet （Optional）",
    "Bridge Pool / Relayer Wallet (Optional)",
]

# Fall back to fixed offset if ZoneInfo missing Asia/Shanghai data
try:
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    from datetime import timezone

    TZ = timezone(timedelta(hours=8))


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"first_seen": {}, "digested_ids": [], "last_digest_date": ""}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"first_seen": {}, "digested_ids": [], "last_digest_date": ""}
    if "digested_ids" not in raw:
        raw["digested_ids"] = []
    return raw


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _today_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def _digest_hour(config: Any) -> int:
    return int(getattr(config, "workflow_lark_digest_hour", 0) or 0)


def _report_date_str(hour: int, now: datetime | None = None) -> str:
    """Calendar day this scheduled digest should summarize (Asia/Shanghai).

    hour=0 (midnight): summarize the day that just ended (yesterday).
    hour>0 (e.g. 22): summarize today after that clock hour.
    """
    now = now or datetime.now(TZ)
    if hour == 0:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")


def _count_addresses(fields: dict[str, Any]) -> int:
    return sum(1 for name in ADDRESS_FIELDS if _field_text(fields, name))


def _append_wallet_event(
    record_id: str,
    project_name: str,
    address_count: int,
    *,
    digest_date: str,
) -> None:
    """Persist a wallet collection event for the dashboard activity feed."""
    now = datetime.now(TZ)
    row = {
        "ts": now.isoformat(timespec="seconds"),
        "day": now.strftime("%Y-%m-%d"),
        "kind": "wallet_collected",
        "source": "lark_wallet_table",
        "record_id": record_id,
        "project_name": project_name or record_id,
        "address_count": int(address_count),
        "digest_date": digest_date,
    }
    path = ROOT / WORKFLOW_EVENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("Lark wallet: failed appending workflow event for %s", record_id)


def _logged_wallet_event_ids(path: Path) -> set[str]:
    """Read record IDs already represented in the append-only wallet event log."""
    if not path.is_file():
        return set()
    out: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("kind") == "wallet_collected":
                    rid = str(row.get("record_id") or "").strip()
                    if rid:
                        out.add(rid)
    except OSError:
        logger.exception("Lark wallet: failed reading workflow event log")
    return out


def _build_digest_text(
    date_str: str,
    projects: list[tuple[str, int]],
    *,
    title: str | None = None,
) -> str:
    project_count = len(projects)
    address_total = sum(n for _, n in projects)
    lines = [
        title or f"【项目方地址日报】{date_str}",
        f"今日新增项目：{project_count} 个",
        f"地址填写数量：{address_total} 个",
        "",
    ]
    if not projects:
        lines.append("今日暂无新的项目方地址写入。")
        return "\n".join(lines)

    lines.append("项目明细：")
    for i, (name, addr_n) in enumerate(projects, 1):
        lines.append(f"{i}. {name} — 地址字段 {addr_n} 个")
    return "\n".join(lines)


async def _seconds_until_next_hour(hour: int) -> float:
    now = datetime.now(TZ)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return max((target - now).total_seconds(), 1.0)


async def sync_wallet_first_seen(config: Any) -> int:
    """Poll wallet table and stamp newly appeared rows with today's date. Returns new count."""
    if not getattr(config, "workflow_enabled", False):
        return 0
    if not getattr(config, "workflow_lark_digest_enabled", False):
        return 0

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return 0

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_wallet_table_id,
    )

    state_path = ROOT / config.workflow_lark_digest_state_file
    state = _load_state(state_path)
    first_seen: dict[str, str] = dict(state.get("first_seen") or {})
    digested: set[str] = {str(x) for x in (state.get("digested_ids") or [])}
    today = _today_str()
    new_n = 0

    # Migration safety: rows detected today before wallet events were introduced
    # should still appear in the dashboard's real activity feed.
    event_path = ROOT / WORKFLOW_EVENTS_FILE
    logged_event_ids = _logged_wallet_event_ids(event_path)
    for record in records:
        rid = str(record.get("record_id") or "")
        if not rid or rid in logged_event_ids or first_seen.get(rid) != today:
            continue
        fields = record.get("fields") or {}
        project_name = _field_text(fields, "Project name").strip()
        address_count = _count_addresses(fields)
        if project_name and address_count:
            _append_wallet_event(
                rid,
                project_name,
                address_count,
                digest_date=today,
            )
            logged_event_ids.add(rid)

    # First run: baseline all current rows so they won't count as "today"
    if not state_path.exists() or not first_seen:
        for record in records:
            rid = str(record.get("record_id") or "")
            if rid:
                first_seen[rid] = "baseline"
                digested.add(rid)
        state["first_seen"] = first_seen
        state["digested_ids"] = sorted(digested)
        _save_state(state_path, state)
        logger.info("Lark digest baseline: %d wallet row(s)", len(first_seen))
        return 0

    # Rows that arrived after a same-day digest was already sent → count tomorrow
    assign_day = today
    if state.get("last_digest_date") == today:
        assign_day = (datetime.now(TZ) + timedelta(days=1)).strftime("%Y-%m-%d")

    new_events: list[dict[str, Any]] = []

    for record in records:
        rid = str(record.get("record_id") or "")
        if not rid or rid in first_seen:
            continue
        fields = record.get("fields") or {}
        project_name = _field_text(fields, "Project name").strip()
        if not project_name:
            continue
        address_count = _count_addresses(fields)
        if address_count == 0:
            continue
        first_seen[rid] = assign_day
        new_n += 1
        new_events.append(
            {
                "record_id": rid,
                "project_name": project_name,
                "address_count": address_count,
                "digest_date": assign_day,
            }
        )

    if new_n:
        state["first_seen"] = first_seen
        state["digested_ids"] = sorted(digested)
        _save_state(state_path, state)
        for event in new_events:
            _append_wallet_event(**event)
        try:
            from bot.metrics import inc

            inc("wallet_digest_new_projects", new_n)
        except Exception:  # noqa: BLE001
            pass
        logger.info("Lark digest tracked %d new wallet row(s) for %s", new_n, assign_day)
    return new_n


async def run_lark_daily_digest_once(config: Any, *, force_date: str | None = None) -> bool:
    """Send today's digest to the configured Lark chat. Returns True if sent."""
    if not getattr(config, "workflow_enabled", False):
        return False
    if not getattr(config, "workflow_lark_digest_enabled", False):
        return False

    chat_id = str(getattr(config, "workflow_lark_digest_chat_id", "") or "").strip()
    if not chat_id:
        logger.warning("lark digest: missing workflow.lark_digest_chat_id")
        return False

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("lark digest skipped: missing LARK credentials")
        return False

    # Ensure latest rows are stamped before summarizing
    await sync_wallet_first_seen(config)

    hour = _digest_hour(config)
    now = datetime.now(TZ)
    if force_date:
        date_str = force_date
    else:
        # Not yet in the send window for non-midnight schedules
        if hour > 0 and now.hour < hour:
            return False
        date_str = _report_date_str(hour, now)

    state_path = ROOT / config.workflow_lark_digest_state_file
    state = _load_state(state_path)
    first_seen: dict[str, str] = dict(state.get("first_seen") or {})
    digested: set[str] = {str(x) for x in (state.get("digested_ids") or [])}

    if state.get("last_digest_date") == date_str and not force_date:
        # Still send if any undigested non-baseline rows exist for this date
        pending = [
            rid
            for rid, day in first_seen.items()
            if day == date_str and rid not in digested
        ]
        if not pending:
            logger.info("Lark digest already sent for %s", date_str)
            return False

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_wallet_table_id,
    )
    by_id = {str(r.get("record_id") or ""): r for r in records}

    projects: list[tuple[str, int]] = []
    included_ids: list[str] = []
    for rid, seen_day in first_seen.items():
        if seen_day != date_str:
            continue
        if rid in digested and not force_date:
            continue
        rec = by_id.get(rid)
        if not rec:
            continue
        fields = rec.get("fields") or {}
        name = _field_text(fields, "Project name") or rid
        projects.append((name, _count_addresses(fields)))
        included_ids.append(rid)

    # force_date path: include all rows for that date even if already digested
    if force_date:
        projects = []
        included_ids = []
        for rid, seen_day in first_seen.items():
            if seen_day != date_str:
                continue
            rec = by_id.get(rid)
            if not rec:
                continue
            fields = rec.get("fields") or {}
            name = _field_text(fields, "Project name") or rid
            projects.append((name, _count_addresses(fields)))
            included_ids.append(rid)

    projects.sort(key=lambda x: x[0].lower())
    text = _build_digest_text(date_str, projects)

    try:
        await loop.run_in_executor(None, send_text_to_chat, token, chat_id, text)
    except Exception:
        logger.exception("Failed to send Lark daily digest to %s", chat_id)
        return False

    digested.update(included_ids)
    # Also treat baseline as digested
    for rid, day in first_seen.items():
        if day == "baseline":
            digested.add(rid)
    state["last_digest_date"] = date_str
    state["first_seen"] = first_seen
    state["digested_ids"] = sorted(digested)
    _save_state(state_path, state)
    try:
        from bot.metrics import inc

        inc("wallet_digest_sent")
    except Exception:  # noqa: BLE001
        pass
    logger.info(
        "Lark digest sent to %s date=%s projects=%d",
        chat_id,
        date_str,
        len(projects),
    )
    append_event(
        "wallet_digest_sent",
        "lark_wallet_digest",
        text=f"钱包日报已发送（{date_str}，{len(projects)} 个项目）",
        digest_date=date_str,
        project_count=len(projects),
        chat_id=chat_id,
    )
    return True


async def lark_digest_loop(config: Any) -> None:
    """Track new rows periodically; send digest every day at configured hour."""
    hour = _digest_hour(config)
    poll_minutes = max(int(getattr(config, "workflow_poll_interval_minutes", 5) or 5), 1)

    while True:
        try:
            await sync_wallet_first_seen(config)
        except Exception:
            logger.exception("Lark digest first_seen sync failed")

        now = datetime.now(TZ)
        state_path = ROOT / getattr(
            config, "workflow_lark_digest_state_file", "data/lark_wallet_digest_state.json"
        )
        state = _load_state(state_path)
        report_date = _report_date_str(hour, now)
        already = state.get("last_digest_date") == report_date
        in_window = hour == 0 or now.hour >= hour
        if in_window and not already:
            try:
                await run_lark_daily_digest_once(config)
            except Exception:
                logger.exception("Lark digest send failed")

        # Sleep until next poll, but wake near digest hour
        seconds_to_digest = await _seconds_until_next_hour(hour)
        sleep_for = min(poll_minutes * 60, seconds_to_digest)
        # If digest is due within 90s, wait exactly then send
        if seconds_to_digest <= 90:
            await asyncio.sleep(seconds_to_digest + 1)
            try:
                await run_lark_daily_digest_once(config)
            except Exception:
                logger.exception("Lark digest send failed at scheduled hour")
            continue
        await asyncio.sleep(sleep_for)


# Backward-compatible aliases used by older main imports
async def run_lark_wallet_group_once(config: Any) -> int:
    await sync_wallet_first_seen(config)
    return 0


async def lark_wallet_group_loop(config: Any) -> None:
    await lark_digest_loop(config)
