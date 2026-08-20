"""Watch Progress Tracker for 主网部署中 / 测试网部署 status transitions.

Baselines on first run; thereafter records enter/leave events (Asia/Shanghai day)
so the daily report can list which projects moved.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.workflow_form_dispatch import _field_text
from bot.workflow_live_trigger import _load_progress_records

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=8))

STATUS_KIND_LIVE = "live"
STATUS_KIND_MAIN_DEPLOY = "main_deploy"
STATUS_KIND_TEST_DEPLOY = "test_deploy"
_WATCHED_KINDS = frozenset(
    {STATUS_KIND_LIVE, STATUS_KIND_MAIN_DEPLOY, STATUS_KIND_TEST_DEPLOY}
)
_EVENT_KEEP_DAYS = 45


def status_kind(status: str) -> str | None:
    s = (status or "").strip()
    if not s:
        return None
    if s.startswith("BOT主网上线") or s.startswith("主网上线"):
        return STATUS_KIND_LIVE
    if s.startswith("主网部署中"):
        return STATUS_KIND_MAIN_DEPLOY
    if s.startswith("测试网部署"):
        return STATUS_KIND_TEST_DEPLOY
    return None


def short_status(status: str) -> str:
    """Human-readable short label for TG reports."""
    s = (status or "").strip()
    if not s:
        return "(空)"
    kind = status_kind(s)
    if kind == STATUS_KIND_LIVE:
        return "主网上线"
    if kind == STATUS_KIND_MAIN_DEPLOY:
        return "主网部署中"
    if kind == STATUS_KIND_TEST_DEPLOY:
        return "测试网部署"
    m = re.match(r"^([^A-Za-z0-9]+)", s)
    if m:
        zh = m.group(1).strip(" /-|·")
        if zh:
            return zh
    return s[:40]


def _state_path(config: "AppConfig") -> Path:
    raw = getattr(config, "workflow_deploy_status_watch_state_file", "") or (
        "data/deploy_status_watch_state.json"
    )
    return ROOT / raw


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"statuses": {}, "events": [], "baselined_at": ""}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"statuses": {}, "events": [], "baselined_at": ""}
    if not isinstance(raw, dict):
        return {"statuses": {}, "events": [], "baselined_at": ""}
    statuses = raw.get("statuses") or {}
    events = raw.get("events") or []
    return {
        "statuses": {str(k): str(v) for k, v in statuses.items() if k},
        "events": [e for e in events if isinstance(e, dict)],
        "baselined_at": str(raw.get("baselined_at") or ""),
    }


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _prune_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff = (datetime.now(TZ).date() - timedelta(days=_EVENT_KEEP_DAYS)).strftime(
        "%Y-%m-%d"
    )
    return [e for e in events if str(e.get("date") or "") >= cutoff]


def _today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _is_relevant(old: str, new: str) -> bool:
    return status_kind(old) in _WATCHED_KINDS or status_kind(new) in _WATCHED_KINDS


def events_for_day(config: "AppConfig", day: str | None = None) -> list[dict[str, Any]]:
    """Return deploy-related status change events for a calendar day."""
    day = day or _today()
    state = _load_state(_state_path(config))
    out = [e for e in state.get("events") or [] if str(e.get("date") or "") == day]
    out.sort(key=lambda e: (str(e.get("ts") or ""), str(e.get("name") or "")))
    return out


def events_since(config: "AppConfig", since: datetime) -> list[dict[str, Any]]:
    """Return deploy-related events with ts >= since (rolling window)."""
    state = _load_state(_state_path(config))
    out: list[dict[str, Any]] = []
    for e in state.get("events") or []:
        ts = _parse_event_ts(e.get("ts"))
        if ts is None:
            # Fallback: calendar day still inside the window's date coverage
            day = str(e.get("date") or "")
            if day and day >= since.strftime("%Y-%m-%d"):
                out.append(e)
            continue
        if ts >= since:
            out.append(e)
    out.sort(key=lambda e: (str(e.get("ts") or ""), str(e.get("name") or "")))
    return out


def _parse_event_ts(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def summarize_day(config: "AppConfig", day: str | None = None) -> dict[str, Any]:
    """Group today's transitions for the daily report."""
    day = day or _today()
    return _summarize_events(config, events_for_day(config, day), date_label=day)


def summarize_window(
    config: "AppConfig",
    *,
    since: datetime | None = None,
    hours: int = 24,
) -> dict[str, Any]:
    """Group transitions in a rolling time window (default past 24 hours)."""
    since = since or (datetime.now(TZ) - timedelta(hours=max(int(hours), 1)))
    return _summarize_events(
        config,
        events_since(config, since),
        date_label=f"{since.isoformat(timespec='seconds')}~now",
        since=since,
    )


def _summarize_events(
    config: "AppConfig",
    events: list[dict[str, Any]],
    *,
    date_label: str,
    since: datetime | None = None,
) -> dict[str, Any]:
    entered_live: list[str] = []
    entered_live_records: list[dict[str, str]] = []
    entered_main: list[str] = []
    left_main: list[str] = []
    entered_test: list[str] = []
    left_test: list[str] = []
    lines: list[str] = []
    for ev in events:
        name = str(ev.get("name") or "(未命名)")
        old = str(ev.get("from") or "")
        new = str(ev.get("to") or "")
        lines.append(f"{name}：{short_status(old)} → {short_status(new)}")
        old_k, new_k = status_kind(old), status_kind(new)
        if new_k == STATUS_KIND_LIVE and old_k != STATUS_KIND_LIVE:
            entered_live.append(name)
            record_id = str(ev.get("record_id") or "").strip()
            if record_id:
                entered_live_records.append({"record_id": record_id, "name": name})
        if new_k == STATUS_KIND_MAIN_DEPLOY and old_k != STATUS_KIND_MAIN_DEPLOY:
            entered_main.append(name)
        if old_k == STATUS_KIND_MAIN_DEPLOY and new_k != STATUS_KIND_MAIN_DEPLOY:
            left_main.append(name)
        if new_k == STATUS_KIND_TEST_DEPLOY and old_k != STATUS_KIND_TEST_DEPLOY:
            entered_test.append(name)
        if old_k == STATUS_KIND_TEST_DEPLOY and new_k != STATUS_KIND_TEST_DEPLOY:
            left_test.append(name)
    return {
        "date": date_label,
        "since": since.isoformat(timespec="seconds") if since else None,
        "total": len(events),
        "events": events,
        "lines": lines,
        "entered_mainnet_live": entered_live,
        "entered_mainnet_live_records": entered_live_records,
        "entered_mainnet_deploy": entered_main,
        "left_mainnet_deploy": left_main,
        "entered_testnet_deploy": entered_test,
        "left_testnet_deploy": left_test,
        "baselined": bool(_load_state(_state_path(config)).get("baselined_at")),
    }


def process_deploy_status_records(
    config: "AppConfig",
    records: list[dict[str, Any]],
) -> int:
    """Diff an already-fetched progress snapshot. Prefer calling from live watch.

    Returns count of new relevant transitions. No Lark network I/O.
    """
    if not getattr(config, "workflow_enabled", False):
        return 0
    if not getattr(config, "workflow_deploy_status_watch_enabled", True):
        return 0

    path = _state_path(config)
    state = _load_state(path)
    first_run = not path.exists() or not state.get("statuses")

    status_field = config.workflow_status_field
    name_field = config.workflow_project_name_field
    current: dict[str, str] = {}
    names: dict[str, str] = {}
    for record in records:
        rid = str(record.get("record_id") or "")
        if not rid:
            continue
        fields = record.get("fields") or {}
        current[rid] = _field_text(fields, status_field)
        names[rid] = _field_text(fields, name_field) or rid

    if first_run:
        state = {
            "statuses": current,
            "events": [],
            "baselined_at": _now_iso(),
        }
        _save_state(path, state)
        logger.info(
            "deploy-status-watch baseline: %d row(s) (no events)",
            len(current),
        )
        return 0

    prev: dict[str, str] = dict(state.get("statuses") or {})
    events: list[dict[str, Any]] = list(state.get("events") or [])
    today = _today()
    new_n = 0

    for rid, new_status in current.items():
        old_status = prev.get(rid)
        if old_status is None:
            # Brand-new row: only record if it starts in a watched status
            if status_kind(new_status) not in _WATCHED_KINDS:
                continue
            old_status = ""
        if old_status == new_status:
            continue
        if not _is_relevant(old_status, new_status):
            continue
        name = names.get(rid) or rid
        ev = {
            "date": today,
            "ts": _now_iso(),
            "record_id": rid,
            "name": name,
            "from": old_status,
            "to": new_status,
        }
        events.append(ev)
        new_n += 1
        logger.info(
            "deploy-status-watch: %r %s → %s",
            name,
            short_status(old_status),
            short_status(new_status),
        )

    state["statuses"] = current
    state["events"] = _prune_events(events)
    if not state.get("baselined_at"):
        state["baselined_at"] = _now_iso()
    _save_state(path, state)

    if new_n:
        try:
            from bot.metrics import inc

            inc("deploy_status_transitions", new_n)
        except Exception:  # noqa: BLE001
            pass
    return new_n


async def run_deploy_status_watch_once(config: "AppConfig") -> int:
    """Standalone poll (only when live-status watch is off)."""
    if not getattr(config, "workflow_enabled", False):
        return 0
    if not getattr(config, "workflow_deploy_status_watch_enabled", True):
        return 0
    try:
        _token, records = await _load_progress_records(config)
    except Exception:
        logger.exception("deploy-status-watch: failed to load Lark records")
        return 0
    return process_deploy_status_records(config, records)


async def deploy_status_watch_loop(config: "AppConfig") -> None:
    """Fallback loop when live-status watch is disabled."""
    interval = max(
        int(getattr(config, "workflow_deploy_status_watch_seconds", 0) or 0)
        or int(getattr(config, "workflow_live_status_watch_seconds", 60) or 60),
        30,
    )
    try:
        await run_deploy_status_watch_once(config)
    except Exception:
        logger.exception("deploy-status-watch initial baseline failed")
    while True:
        await asyncio.sleep(interval)
        try:
            await run_deploy_status_watch_once(config)
        except Exception:
            logger.exception("deploy-status-watch loop error")
