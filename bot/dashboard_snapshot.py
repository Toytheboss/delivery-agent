"""Build / load Delivery Agent dashboard snapshot (hourly, disk-backed)."""

from __future__ import annotations

import json
import logging
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

try:
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _day_list(n: int) -> list[str]:
    end = datetime.now(TZ).date()
    return [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n - 1, -1, -1)]


def _message_log_dir(config: Any) -> Path:
    raw = getattr(config, "metrics_message_log_dir", "data/message_logs")
    path = Path(str(raw))
    return path if path.is_absolute() else ROOT / path


def _scan_message_logs(
    config: Any,
    *,
    lookback_days: int,
    list_limit: int,
) -> dict[str, Any]:
    """Stream JSONL day files; keep newest answered/silent rows + reason counts."""
    log_dir = _message_log_dir(config)
    days = _day_list(max(int(lookback_days), 1))
    answered: deque[dict[str, Any]] = deque(maxlen=max(int(list_limit), 1))
    silent: deque[dict[str, Any]] = deque(maxlen=max(int(list_limit), 1))
    reasons: Counter[str] = Counter()
    scanned_files = 0
    scanned_lines = 0

    for day in days:
        path = log_dir / f"messages-{day}.jsonl"
        if not path.is_file():
            continue
        scanned_files += 1
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    scanned_lines += 1
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    outcome = str(row.get("outcome") or "")
                    reason = str(row.get("reason") or "") or "(empty)"
                    item = {
                        "ts": row.get("ts") or "",
                        "chat_title": (row.get("chat_title") or "")[:120],
                        "text": (row.get("text") or "")[:500],
                        "reply_text": (row.get("reply_text") or "")[:800],
                        "reason": reason[:200],
                        "score": row.get("score"),
                        "kind": row.get("kind") or "",
                    }
                    if outcome == "replied":
                        answered.append(item)
                    elif outcome == "silent":
                        silent.append(item)
                        reasons[reason] += 1
        except OSError:
            logger.exception("dashboard: failed reading %s", path)

    return {
        "answered": list(reversed(answered)),
        "silent": list(reversed(silent)),
        "silence_reasons": dict(reasons.most_common(40)),
        "scanned_files": scanned_files,
        "scanned_lines": scanned_lines,
        "lookback_days": lookback_days,
        "list_limit": list_limit,
    }


def _counter_series(config: Any) -> dict[str, Any]:
    from bot.metrics import COUNTER_KEYS, get_counter

    out: dict[str, Any] = {}
    for key in COUNTER_KEYS:
        c = get_counter(key)
        out[key] = {
            "total": int(c.get("total") or 0),
            "by_day": dict(c.get("by_day") or {}),
        }
    return out


def build_dashboard_snapshot(
    config: Any,
    *,
    include_lark: bool = True,
    lookback_days: int | None = None,
    list_limit: int | None = None,
) -> dict[str, Any]:
    lookback = int(
        lookback_days
        if lookback_days is not None
        else getattr(config, "dashboard_qa_lookback_days", 7) or 7
    )
    limit = int(
        list_limit
        if list_limit is not None
        else getattr(config, "dashboard_list_limit", 150) or 150
    )

    from bot.metrics import build_daily_report, snapshot

    snap = snapshot(config, include_lark=include_lark)
    daily: dict[str, Any] = {}
    try:
        daily = build_daily_report(config)
    except Exception:  # noqa: BLE001
        logger.exception("dashboard: build_daily_report failed")
        daily = {"error": "build_daily_report_failed"}

    qa = _scan_message_logs(config, lookback_days=lookback, list_limit=limit)
    series = _counter_series(config)

    return {
        "generated_at": _now_iso(),
        "timezone": "Asia/Shanghai",
        "window": {"qa_days": lookback, "list_limit": limit},
        "metrics_updated_at": snap.get("updated_at") or "",
        "snapshot": snap,
        "daily": daily,
        "counters_series": series,
        "qa": qa,
    }


def snapshot_path(config: Any | None = None) -> Path:
    raw = getattr(config, "dashboard_snapshot_file", None) if config else None
    path = Path(str(raw or "data/dashboard_snapshot.json"))
    return path if path.is_absolute() else ROOT / path


def write_dashboard_snapshot(config: Any, payload: dict[str, Any] | None = None) -> Path:
    path = snapshot_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = payload if payload is not None else build_dashboard_snapshot(config)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_dashboard_snapshot(config: Any | None = None) -> dict[str, Any] | None:
    path = snapshot_path(config)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def snapshot_age_seconds(config: Any | None = None) -> float | None:
    path = snapshot_path(config)
    if not path.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=TZ)
        return max(0.0, (datetime.now(TZ) - mtime).total_seconds())
    except OSError:
        return None
