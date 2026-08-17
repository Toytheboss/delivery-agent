"""Build / load Delivery Agent dashboard snapshot (hourly, disk-backed)."""

from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict, deque
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
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    """Stream JSONL day files; keep newest answered/silent rows + reason counts."""
    log_dir = _message_log_dir(config)
    days = _day_list(max(int(lookback_days), 1))
    answered: deque[dict[str, Any]] = deque(maxlen=max(int(list_limit), 1))
    silent: deque[dict[str, Any]] = deque(maxlen=max(int(list_limit), 1))
    reasons: Counter[str] = Counter()
    scanned_files = 0
    scanned_lines = 0
    replied_n = silent_n = other_n = 0

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
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if since is not None or until is not None:
                        event_dt = _event_datetime(row.get("ts"))
                        if event_dt is not None and (
                            (since is not None and event_dt < since)
                            or (until is not None and event_dt > until)
                        ):
                            continue
                    scanned_lines += 1
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
                        replied_n += 1
                        answered.append(item)
                    elif outcome == "silent":
                        silent_n += 1
                        silent.append(item)
                        reasons[reason] += 1
                    else:
                        other_n += 1
        except OSError:
            logger.exception("dashboard: failed reading %s", path)

    return {
        "answered": list(reversed(answered)),
        "silent": list(reversed(silent)),
        "silence_reasons": dict(reasons.most_common(40)),
        "counts": {
            "replied": replied_n,
            "silent": silent_n,
            "other": other_n,
            "lines": scanned_lines,
        },
        "scanned_files": scanned_files,
        "scanned_lines": scanned_lines,
        "lookback_days": lookback_days,
        "list_limit": list_limit,
    }


def _scan_one_day(
    config: Any,
    day: str,
    *,
    list_limit: int,
) -> dict[str, Any]:
    """Stream a single day JSONL file into answered/silent lists + counts."""
    log_dir = _message_log_dir(config)
    path = log_dir / f"messages-{day}.jsonl"
    answered_all: list[dict[str, Any]] = []
    silent_all: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    lines = replied = silent_n = other = 0
    if not path.is_file():
        return {
            "date": day,
            "exists": False,
            "answered": [],
            "silent": [],
            "silence_reasons": {},
            "counts": {"replied": 0, "silent": 0, "other": 0, "lines": 0},
            "list_limit": list_limit,
        }
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                lines += 1
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
                    replied += 1
                    answered_all.append(item)
                elif outcome == "silent":
                    silent_n += 1
                    silent_all.append(item)
                    reasons[reason] += 1
                else:
                    other += 1
    except OSError:
        logger.exception("dashboard: failed reading %s", path)

    limit = max(int(list_limit), 1)
    answered = list(reversed(answered_all))[:limit]
    silent = list(reversed(silent_all))[:limit]
    return {
        "date": day,
        "exists": True,
        "answered": answered,
        "silent": silent,
        "silence_reasons": dict(reasons.most_common(40)),
        "counts": {
            "replied": replied,
            "silent": silent_n,
            "other": other,
            "lines": lines,
        },
        "list_limit": list_limit,
    }


def _counter_series(config: Any) -> dict[str, Any]:
    """Per-counter totals + by_day maps (padded empty days omitted; UI fills range)."""
    del config
    from bot.metrics import COUNTER_KEYS, get_counter_series

    return get_counter_series(list(COUNTER_KEYS))


def build_calendar_activity(config: Any, *, days: int = 30) -> dict[str, Any]:
    """Count-only scan of last N day logs for calendar heatmap (cheap)."""
    days_n = max(min(int(days), 90), 1)
    log_dir = _message_log_dir(config)
    series = _counter_series(config)
    heat: list[list[Any]] = []  # [date, activity]
    per_day: list[dict[str, Any]] = []
    for day in _day_list(days_n):
        path = log_dir / f"messages-{day}.jsonl"
        replied = silent = other = 0
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(row, dict):
                            continue
                        outcome = str(row.get("outcome") or "")
                        if outcome == "replied":
                            replied += 1
                        elif outcome == "silent":
                            silent += 1
                        else:
                            other += 1
            except OSError:
                logger.exception("dashboard calendar: failed reading %s", path)
        faq = int((series.get("faq_reply_sessions") or {}).get("by_day", {}).get(day) or 0)
        processed = int((series.get("messages_processed") or {}).get("by_day", {}).get(day) or 0)
        form_ok = int((series.get("form_dispatch_success") or {}).get("by_day", {}).get(day) or 0)
        logo_ok = int((series.get("logo_fill_success") or {}).get("by_day", {}).get(day) or 0)
        # Heat: prefer Q&A log outcomes; without logs use processed messages only
        # (do not fall back to faq_reply_sessions — one spike washes out the calendar).
        activity = replied + silent
        if activity == 0:
            activity = processed
        heat.append([day, activity])
        per_day.append(
            {
                "date": day,
                "replied": replied,
                "silent": silent,
                "other": other,
                "activity": activity,
                "faq_sessions": faq,
                "messages_processed": processed,
                "form_ok": form_ok,
                "logo_ok": logo_ok,
                "has_log": path.is_file(),
            }
        )
    start = per_day[0]["date"] if per_day else _day_list(1)[0]
    end = per_day[-1]["date"] if per_day else start
    return {
        "range_days": days_n,
        "start": start,
        "end": end,
        "heat": heat,
        "days": per_day,
    }


def _logo_events_path(config: Any) -> Path:
    raw = getattr(config, "workflow_logo_events_file", "data/logo_fill_events.jsonl")
    path = Path(str(raw))
    return path if path.is_absolute() else ROOT / path


def _logo_status_bucket(status: str) -> str:
    s = str(status or "")
    if s.startswith("ok"):
        return "success"
    if s in {"no_logo", "no_url"}:
        return "no_logo"
    if s.startswith("err") or s.startswith("fail"):
        return "fail"
    if s in {"already_has_logo", "baseline_has_logo", "disabled", "already_processed"}:
        return "skip"
    return "other"


def _day_logo_detail(config: Any, day: str, series: dict[str, Any]) -> dict[str, Any]:
    """Logo fetch outcomes for one day: metric counts + named event rows."""
    counts = {
        "success": int((series.get("logo_fill_success") or {}).get("by_day", {}).get(day) or 0),
        "fail": int((series.get("logo_fill_fail") or {}).get("by_day", {}).get(day) or 0),
        "no_logo": int((series.get("logo_fill_no_logo") or {}).get("by_day", {}).get(day) or 0),
    }
    items: list[dict[str, Any]] = []
    path = _logo_events_path(config)
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("day") or "") != day:
                        continue
                    status = str(row.get("status") or "")
                    items.append(
                        {
                            "ts": row.get("ts") or "",
                            "record_id": row.get("record_id") or "",
                            "project_name": (row.get("project_name") or "")[:120]
                            or (row.get("record_id") or ""),
                            "status": status[:200],
                            "bucket": _logo_status_bucket(status),
                        }
                    )
        except OSError:
            logger.exception("dashboard: failed reading logo events %s", path)
    items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    by_bucket: Counter[str] = Counter(str(x.get("bucket") or "other") for x in items)
    return {
        "counts": counts,
        "items": items[:200],
        "item_count": len(items),
        "by_bucket": dict(by_bucket),
        "note": (
            None
            if items or (counts["success"] + counts["fail"] + counts["no_logo"]) == 0
            else "当日有埋点计数，但尚无带项目名的事件日志（新抓取后会写入）。"
        ),
    }


_WALLET_TYPE_LABELS = {
    "Contract Addresss/主网合约": "主网合约",
    "Treasury Address": "Treasury",
    "Fee Collector / Revenue Wallet Address": "Fee Collector",
    "Grant Receiving Wallet (Optional)": "Grant",
    "MM / LP Wallet （Optional）": "MM/LP",
    "Bridge Pool / Relayer Wallet (Optional)": "Bridge/Relayer",
}
_ADDRESS_FIELDS = list(_WALLET_TYPE_LABELS.keys())


def _day_wallet_detail(config: Any, day: str) -> dict[str, Any]:
    """New wallet projects first-seen on this day, with type → address + project name."""
    digest_path = ROOT / str(
        getattr(
            config,
            "workflow_lark_digest_state_file",
            "data/lark_wallet_digest_state.json",
        )
    )
    first_seen: dict[str, str] = {}
    if digest_path.is_file():
        try:
            raw = json.loads(digest_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                first_seen = {
                    str(k): str(v)
                    for k, v in (raw.get("first_seen") or {}).items()
                    if k and str(v) not in {"", "baseline"}
                }
        except (OSError, json.JSONDecodeError):
            first_seen = {}

    day_ids = {rid for rid, seen in first_seen.items() if seen == day}
    out: dict[str, Any] = {
        "new_projects": len(day_ids),
        "address_fields_filled": 0,
        "by_type": {label: 0 for label in _WALLET_TYPE_LABELS.values()},
        "items": [],
        "error": None,
    }
    if not day_ids:
        return out

    import os

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        out["error"] = "missing LARK credentials"
        out["items"] = [
            {
                "record_id": rid,
                "project_name": rid,
                "address_count": 0,
                "wallets": [],
            }
            for rid in sorted(day_ids)
        ]
        return out

    try:
        from bot.lark_bitable import get_tenant_access_token, list_records
        from bot.workflow_form_dispatch import _field_text

        token = get_tenant_access_token(app_id, app_secret)
        records = list_records(
            token,
            str(getattr(config, "workflow_base_app_token", "")),
            str(getattr(config, "workflow_wallet_table_id", "")),
        )
        items: list[dict[str, Any]] = []
        addr_total = 0
        by_type: Counter[str] = Counter()
        seen_left = set(day_ids)
        for record in records:
            rid = str(record.get("record_id") or "")
            if rid not in day_ids:
                continue
            fields = record.get("fields") or {}
            name = _field_text(fields, "Project name") or rid
            wallets: list[dict[str, str]] = []
            for fname in _ADDRESS_FIELDS:
                val = _field_text(fields, fname)
                if not val:
                    continue
                label = _WALLET_TYPE_LABELS.get(fname, fname)
                wallets.append(
                    {
                        "type": label,
                        "field": fname,
                        "value": val[:80],
                    }
                )
                by_type[label] += 1
                addr_total += 1
            items.append(
                {
                    "record_id": rid,
                    "project_name": name[:120],
                    "address_count": len(wallets),
                    "wallets": wallets,
                }
            )
            seen_left.discard(rid)
        for rid in sorted(seen_left):
            items.append(
                {
                    "record_id": rid,
                    "project_name": rid,
                    "address_count": 0,
                    "wallets": [],
                }
            )
        items.sort(key=lambda x: (-int(x.get("address_count") or 0), str(x.get("project_name") or "")))
        out["items"] = items
        out["new_projects"] = len(items)
        out["address_fields_filled"] = addr_total
        out["by_type"] = {
            label: int(by_type.get(label, 0)) for label in _WALLET_TYPE_LABELS.values()
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("dashboard: day wallet detail failed: %s", exc)
        out["error"] = str(exc)
    return out


def build_day_detail(config: Any, day: str, *, list_limit: int | None = None) -> dict[str, Any]:
    """Full revisit payload for one Asia/Shanghai calendar day."""
    day = str(day or "").strip()
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date must be YYYY-MM-DD") from exc

    retain = int(getattr(config, "metrics_message_log_retain_days", 60) or 60)
    allowed = set(_day_list(max(retain, 1)))
    if day not in allowed:
        raise ValueError(f"date out of retain window ({retain} days)")

    limit = int(
        list_limit
        if list_limit is not None
        else getattr(config, "dashboard_list_limit", 150) or 150
    )
    qa = _scan_one_day(config, day, list_limit=limit)
    series = _counter_series(config)
    metrics_day = {
        key: int((series.get(key) or {}).get("by_day", {}).get(day) or 0)
        for key in (
            "faq_reply_sessions",
            "faq_bubbles_sent",
            "messages_processed",
            "social_chitchat_replies",
            "welcome_sequences_started",
            "welcome_messages_sent",
            "form_dispatch_success",
            "logo_fill_success",
            "logo_fill_fail",
            "logo_fill_no_logo",
            "mark_live_triggers",
            "absorb_learn_success",
            "webhook_live_received",
            "webhook_live_processed",
            "wallet_digest_new_projects",
        )
    }
    logos = _day_logo_detail(config, day, series)
    wallets = _day_wallet_detail(config, day)
    return {
        "generated_at": _now_iso(),
        "timezone": "Asia/Shanghai",
        "date": day,
        "retain_days": retain,
        "metrics": metrics_day,
        "qa": qa,
        "logos": logos,
        "wallets": wallets,
    }


def build_range_summary(
    config: Any,
    days: int,
    *,
    series: dict[str, Any] | None = None,
    list_limit: int | None = None,
) -> dict[str, Any]:
    """Aggregate QA + workflow metrics over the last N Asia/Shanghai days."""
    days_n = max(min(int(days), 90), 1)
    day_list = _day_list(days_n)
    limit = int(
        list_limit
        if list_limit is not None
        else getattr(config, "dashboard_list_limit", 150) or 150
    )
    series = series if series is not None else _counter_series(config)
    qa = _scan_message_logs(config, lookback_days=days_n, list_limit=limit)

    metric_keys = (
        "faq_reply_sessions",
        "messages_processed",
        "messages_sent",
        "form_dispatch_success",
        "logo_fill_success",
        "logo_fill_fail",
        "logo_fill_no_logo",
        "welcome_sequences_started",
        "mark_live_triggers",
        "folder_auto_add_success",
        "wallet_digest_new_projects",
        "absorb_learn_success",
    )
    metrics: dict[str, int] = {}
    for key in metric_keys:
        by_day = (series.get(key) or {}).get("by_day") or {}
        metrics[key] = sum(int(by_day.get(d) or 0) for d in day_list)

    # Logo named rows across range
    logo_items: list[dict[str, Any]] = []
    logo_path = _logo_events_path(config)
    day_set = set(day_list)
    if logo_path.is_file():
        try:
            with logo_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if str(row.get("day") or "") not in day_set:
                        continue
                    status = str(row.get("status") or "")
                    logo_items.append(
                        {
                            "ts": row.get("ts") or "",
                            "record_id": row.get("record_id") or "",
                            "project_name": (row.get("project_name") or "")[:120]
                            or (row.get("record_id") or ""),
                            "status": status[:200],
                            "bucket": _logo_status_bucket(status),
                        }
                    )
        except OSError:
            logger.exception("dashboard: failed reading logo events for range")
    logo_items.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    logo_by = Counter(str(x.get("bucket") or "other") for x in logo_items)

    digest_path = ROOT / str(
        getattr(
            config,
            "workflow_lark_digest_state_file",
            "data/lark_wallet_digest_state.json",
        )
    )
    wallet_new = 0
    if digest_path.is_file():
        try:
            raw = json.loads(digest_path.read_text(encoding="utf-8"))
            first_seen = (raw.get("first_seen") or {}) if isinstance(raw, dict) else {}
            wallet_new = sum(
                1
                for day in first_seen.values()
                if str(day) in day_set and str(day) not in {"", "baseline"}
            )
        except (OSError, json.JSONDecodeError):
            wallet_new = 0

    return {
        "days": days_n,
        "start": day_list[0],
        "end": day_list[-1],
        "metrics": metrics,
        "qa": {
            "counts": qa.get("counts") or {},
            "silence_reasons": qa.get("silence_reasons") or {},
            "answered": qa.get("answered") or [],
            "silent": qa.get("silent") or [],
            "list_limit": limit,
        },
        "logos": {
            "counts": {
                "success": int(metrics.get("logo_fill_success") or 0),
                "fail": int(metrics.get("logo_fill_fail") or 0),
                "no_logo": int(metrics.get("logo_fill_no_logo") or 0),
            },
            "items": logo_items[:100],
            "item_count": len(logo_items),
            "by_bucket": dict(logo_by),
        },
        "wallets": {
            "new_projects": wallet_new,
        },
    }


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
        else getattr(config, "dashboard_qa_lookback_days", 30) or 30
    )
    limit = int(
        list_limit
        if list_limit is not None
        else getattr(config, "dashboard_list_limit", 150) or 150
    )
    calendar_days = int(getattr(config, "dashboard_calendar_days", 30) or 30)
    calendar_days = max(min(calendar_days, 90), 7)

    from bot.metrics import build_period_reports, snapshot

    snap = snapshot(config, include_lark=include_lark)
    period_reports: dict[str, Any] = {}
    try:
        period_reports = build_period_reports(config)
    except Exception:  # noqa: BLE001
        logger.exception("dashboard: build_period_reports failed")
        period_reports = {"24h": {"error": "build_period_reports_failed"}}
    daily = period_reports.get("24h") or {"error": "missing_24h"}

    qa = _scan_message_logs(config, lookback_days=lookback, list_limit=limit)
    qa_24h = _scan_message_logs(
        config,
        lookback_days=2,
        list_limit=limit,
        since=datetime.now(TZ) - timedelta(hours=24),
    )
    series = _counter_series(config)
    calendar = build_calendar_activity(config, days=calendar_days)
    ranges = {
        "7": build_range_summary(config, 7, series=series, list_limit=limit),
        "30": build_range_summary(config, 30, series=series, list_limit=limit),
    }
    # Keep the rolling range reports and the analytics page on the same real
    # message-log source for silence counts and reason breakdowns.
    period_reports.setdefault("24h", {})["qa"] = {
        "counts": qa_24h.get("counts") or {},
        "silence_reasons": qa_24h.get("silence_reasons") or {},
        "answered": qa_24h.get("answered") or [],
        "silent": qa_24h.get("silent") or [],
        "list_limit": limit,
    }
    period_reports.setdefault("7d", {})["qa"] = ranges["7"].get("qa") or {}
    period_reports.setdefault("30d", {})["qa"] = ranges["30"].get("qa") or {}
    automation = build_automation_tasks(
        config,
        {
            "snapshot": snap,
            "qa": qa,
            "generated_at": _now_iso(),
        },
    )

    return {
        "generated_at": _now_iso(),
        "timezone": "Asia/Shanghai",
        "window": {
            "qa_days": lookback,
            "list_limit": limit,
            "calendar_days": calendar_days,
        },
        "metrics_updated_at": snap.get("updated_at") or "",
        "snapshot": snap,
        "daily": daily,
        "period_reports": period_reports,
        "counters_series": series,
        "qa": qa,
        "calendar": calendar,
        "ranges": ranges,
        "automation": automation,
    }


def build_live_project_rows(config: Any) -> dict[str, Any]:
    """Read the Lark progress table and join it with the Bot's TG title cache.

    The browser never receives Lark credentials.  This function runs on the Bot
    server and exposes only the fields needed by the admin console.
    """
    out: dict[str, Any] = {
        "generated_at": _now_iso(),
        "total": 0,
        "matched": 0,
        "matched_unique": 0,
        "ambiguous": 0,
        "status_options": [],
        "rows": [],
        "error": None,
    }
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        out["error"] = "missing LARK credentials"
        return out

    try:
        from bot.lark_bitable import get_tenant_access_token, list_fields, list_records
        from bot.workflow_form_dispatch import (
            _field_text,
            _normalize_name,
            find_project_chat_matches,
        )

        token = get_tenant_access_token(app_id, app_secret)
        records = list_records(
            token,
            str(getattr(config, "workflow_base_app_token", "")),
            str(getattr(config, "workflow_progress_table_id", "")),
        )
        status_field_name = str(
            getattr(config, "workflow_status_field", "项目状态") or "项目状态"
        )
        status_options: list[dict[str, Any]] = []
        try:
            field_defs = list_fields(
                token,
                str(getattr(config, "workflow_base_app_token", "")),
                str(getattr(config, "workflow_progress_table_id", "")),
            )
            status_field_def = next(
                (
                    field
                    for field in field_defs
                    if str(field.get("field_name") or "") == status_field_name
                ),
                None,
            )
            for option in ((status_field_def or {}).get("property") or {}).get("options") or []:
                option_name = str(option.get("name") or "").strip()
                if not option_name:
                    continue
                status_options.append(
                    {
                        "id": str(option.get("id") or ""),
                        "name": option_name,
                        "color": option.get("color"),
                        "source": "lark_field",
                    }
                )
        except Exception:  # noqa: BLE001
            logger.exception("dashboard: failed loading Lark status field options")

        def load_state(attr: str, default: str) -> dict[str, Any]:
            path = _dashboard_path(config, attr, default)
            if not path.is_file():
                return {}
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError):
                return {}
            return raw if isinstance(raw, dict) else {}

        def event_iso(value: Any) -> str:
            parsed = _event_datetime(value)
            return parsed.isoformat(timespec="seconds") if parsed is not None else ""

        def project_key(value: Any) -> str:
            return _normalize_name(str(value or ""))

        def step(
            key: str,
            title: str,
            state: str,
            detail: str,
            *,
            ts: Any = None,
            source: str = "",
        ) -> dict[str, Any]:
            return {
                "key": key,
                "title": title,
                "state": state,
                "detail": detail,
                "ts": event_iso(ts),
                "source": source,
            }

        # Durable workflow state is the source of truth for completion.  Event
        # logs provide timestamps and audit evidence where available.  Keeping
        # both prevents old projects from reverting to "pending" merely because
        # their event predates the append-only event feed.
        form_dispatch_state = load_state(
            "workflow_state_file", "data/form_dispatch_state.json"
        )
        form_chase_state = load_state(
            "workflow_form_chase_state_file", "data/form_chase_state.json"
        )
        welcome_state = load_state(
            "welcome_state_file", "data/group_welcome_state.json"
        )
        logo_state = load_state(
            "workflow_logo_state_file", "data/logo_fill_state.json"
        )
        wallet_digest_state = load_state(
            "workflow_lark_digest_state_file", "data/lark_wallet_digest_state.json"
        )
        sent_ids = {
            str(item) for item in (form_dispatch_state.get("sent_record_ids") or [])
        }
        greeted_chat_ids: set[int] = set()
        for item in welcome_state.get("greeted_chat_ids") or []:
            try:
                greeted_chat_ids.add(int(item))
            except (TypeError, ValueError):
                continue
        logo_results = {
            str(key): str(value)
            for key, value in (logo_state.get("results") or {}).items()
        }
        digested_wallet_ids = {
            str(item) for item in (wallet_digest_state.get("digested_ids") or [])
        }
        wallet_first_seen = {
            str(key): str(value)
            for key, value in (wallet_digest_state.get("first_seen") or {}).items()
        }

        # The wallet digest state stores wallet-table record IDs, so fetch that
        # table once and join it by the normalized project name.
        wallet_records: list[dict[str, Any]] = []
        wallet_table_id = str(getattr(config, "workflow_wallet_table_id", "") or "")
        if wallet_table_id:
            try:
                wallet_records = list_records(
                    token,
                    str(getattr(config, "workflow_base_app_token", "")),
                    wallet_table_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception("dashboard: wallet table join failed")
        wallet_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for wallet_record in wallet_records:
            wallet_fields = wallet_record.get("fields") or {}
            wallet_name = _field_text(wallet_fields, "Project name")
            if project_key(wallet_name):
                wallet_by_name[project_key(wallet_name)].append(wallet_record)

        chase_by_name: dict[str, dict[str, Any]] = {}
        chase_projects = form_chase_state.get("projects") or {}
        if isinstance(chase_projects, dict):
            for meta in chase_projects.values():
                if not isinstance(meta, dict):
                    continue
                key = project_key(meta.get("project_name"))
                if key:
                    chase_by_name[key] = meta

        # Index all persisted workflow evidence by record, TG chat, and exact
        # normalized project name.  Name matching here is intentionally exact;
        # fuzzy matching is used only when binding Lark projects to TG groups.
        indexed_events: list[dict[str, Any]] = []
        workflow_events_path = _dashboard_path(
            config, "workflow_events_file", "data/workflow_events.jsonl"
        )
        for item in _read_jsonl(workflow_events_path, max_days=3650):
            kind = str(item.get("kind") or "automation")
            event_text = str(item.get("text") or "").strip()
            if not event_text and kind == "wallet_collected":
                address_count = int(item.get("address_count") or 0)
                count_text = f"（{address_count} 个地址字段）" if address_count else ""
                event_text = f"{item.get('project_name') or item.get('record_id') or '项目'} 的钱包地址已自动收集到 Lark{count_text}"
            elif not event_text and kind == "wallet_notified":
                event_text = f"{item.get('project_name') or item.get('record_id') or '项目'} 的钱包资料已推送至部门群"
            indexed_events.append(
                {
                    **item,
                    "kind": kind,
                    "text": event_text,
                    "ts": event_iso(item.get("ts")),
                    "source": str(item.get("source") or "workflow_events"),
                    "status": str(item.get("status") or "success"),
                }
            )

        logo_events_path = _dashboard_path(
            config, "workflow_logo_events_file", "data/logo_fill_events.jsonl"
        )
        for item in _read_jsonl(logo_events_path, max_days=3650):
            logo_status = str(item.get("status") or "")
            if logo_status.startswith("ok"):
                logo_text = f"{item.get('project_name') or item.get('record_id') or '项目'} 的 Logo 已写入 Lark"
                status = "success"
            elif logo_status in {"no_logo", "no_url"}:
                logo_text = f"{item.get('project_name') or item.get('record_id') or '项目'} 未找到可用 Logo"
                status = "warning"
            else:
                logo_text = f"{item.get('project_name') or item.get('record_id') or '项目'} 的 Logo 处理失败"
                status = "error"
            indexed_events.append(
                {
                    **item,
                    "kind": "logo_uploaded_lark",
                    "text": logo_text,
                    "ts": event_iso(item.get("ts")),
                    "source": "logo_fill",
                    "status": status,
                }
            )

        deploy_state = load_state(
            "workflow_deploy_status_watch_state_file",
            "data/deploy_status_watch_state.json",
        )
        for item in deploy_state.get("events") or []:
            if not isinstance(item, dict):
                continue
            status_text = _short_workflow_status(str(item.get("to") or ""))
            indexed_events.append(
                {
                    "kind": "lark_status_changed",
                    "record_id": str(item.get("record_id") or ""),
                    "project_name": str(item.get("name") or ""),
                    "text": f"{item.get('name') or item.get('record_id') or '项目'} 状态更新为 {status_text}",
                    "ts": event_iso(item.get("ts")),
                    "source": "lark_status",
                    "status": "success",
                }
            )

        events_by_record: dict[str, list[dict[str, Any]]] = defaultdict(list)
        events_by_chat: dict[int, list[dict[str, Any]]] = defaultdict(list)
        events_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in indexed_events:
            record_id = str(item.get("record_id") or "")
            if record_id:
                events_by_record[record_id].append(item)
            try:
                event_chat_id = int(item.get("chat_id"))
            except (TypeError, ValueError):
                event_chat_id = 0
            if event_chat_id:
                events_by_chat[event_chat_id].append(item)
            name_key = project_key(item.get("project_name"))
            if name_key:
                events_by_name[name_key].append(item)

        # Per-project Telegram QA evidence for the latest 30 days. We count
        # every row but retain only the newest 30 events per chat for the drawer.
        qa_by_chat: dict[int, dict[str, Any]] = defaultdict(
            lambda: {
                "replied": 0,
                "silent": 0,
                "last_ts": "",
                "events": deque(maxlen=30),
            }
        )
        for day in _day_list(30):
            message_path = _message_log_dir(config) / f"messages-{day}.jsonl"
            if not message_path.is_file():
                continue
            try:
                with message_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            message = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(message, dict):
                            continue
                        try:
                            message_chat_id = int(message.get("chat_id"))
                        except (TypeError, ValueError):
                            continue
                        outcome = str(message.get("outcome") or "")
                        if outcome not in {"replied", "silent"}:
                            continue
                        evidence = qa_by_chat[message_chat_id]
                        evidence[outcome] += 1
                        message_ts = event_iso(message.get("ts"))
                        if message_ts > str(evidence.get("last_ts") or ""):
                            evidence["last_ts"] = message_ts
                        text_preview = str(message.get("text") or "").strip()[:80]
                        if outcome == "replied":
                            evidence["events"].append(
                                {
                                    "kind": "qa_replied",
                                    "text": "Bot 回答了一条项目问题"
                                    + (f"：{text_preview}" if text_preview else ""),
                                    "ts": message_ts,
                                    "source": "telegram_qa",
                                    "status": "success",
                                }
                            )
                        else:
                            reason = str(
                                message.get("silent_reason")
                                or message.get("reason")
                                or ""
                            ).strip()
                            evidence["events"].append(
                                {
                                    "kind": "qa_silent",
                                    "text": "Bot 未自动回复一条项目问题"
                                    + (f"：{text_preview}" if text_preview else "")
                                    + (f"（{reason}）" if reason else ""),
                                    "ts": message_ts,
                                    "source": "telegram_qa",
                                    "status": "warning",
                                }
                            )
            except OSError:
                logger.exception("dashboard: failed reading project QA evidence %s", message_path)

        title_cache: dict[int, str] = {}
        cache_path = ROOT / "data" / "folder_title_cache.json"
        if cache_path.is_file():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            for key, value in (raw.get("titles") or {}).items():
                try:
                    chat_id = int(key)
                except (TypeError, ValueError):
                    continue
                title = value.get("title") if isinstance(value, dict) else value
                if str(title or "").strip():
                    title_cache[chat_id] = str(title).strip()

        status_field = status_field_name
        name_field = str(
            getattr(config, "workflow_project_name_field", "项目名称 Project Name")
            or "项目名称 Project Name"
        )
        bd_field = "BD"
        delivery_field = "交付"
        update_field = "更新日期"
        ignored_ids = set(getattr(config, "ignored_group_ids", set()) or set())
        rows: list[dict[str, Any]] = []

        def stage(status: str) -> tuple[str, str]:
            text = status.lower()
            if "主网上线" in status or "live on" in text:
                return "live", "主网上线"
            if "主网部署" in status or "mainnet" in text and "deploy" in text:
                return "main_deploy", "主网部署中"
            if "测试网部署" in status or "testnet" in text and "deploy" in text:
                return "test_deploy", "测试网部署"
            return "other", status or "未设置"

        for record in records:
            fields = record.get("fields") or {}
            name = _field_text(fields, name_field)
            if not name:
                continue
            status_raw = _field_text(fields, status_field)
            stage_key, stage_label = stage(status_raw)
            chat_matches = find_project_chat_matches(name, title_cache)
            chat_id = chat_matches[0][0] if chat_matches else None
            chat_title = chat_matches[0][1] if chat_matches else ""
            match_reason = chat_matches[0][3] if chat_matches else "no fuzzy title match"
            if len(chat_matches) > 1:
                match_reason = f"ambiguous fuzzy title matches: {[item[0] for item in chat_matches]}"
            bd = _field_text(fields, bd_field)
            delivery = _field_text(fields, delivery_field)
            updated = fields.get(update_field)
            record_id = str(record.get("record_id") or "")
            name_key = project_key(name)
            wallet_candidates = wallet_by_name.get(name_key) or []
            wallet_record = max(
                wallet_candidates,
                key=lambda item: sum(
                    1
                    for value in (item.get("fields") or {}).values()
                    if _field_text({"value": value}, "value")
                ),
                default=None,
            )
            wallet_record_id = str((wallet_record or {}).get("record_id") or "")
            wallet_fields = (wallet_record or {}).get("fields") or {}
            chase_meta = (
                chase_projects.get(record_id)
                if isinstance(chase_projects, dict)
                else None
            )
            if not isinstance(chase_meta, dict):
                chase_meta = chase_by_name.get(name_key) or {}

            project_events: list[dict[str, Any]] = []
            project_events.extend(events_by_record.get(record_id) or [])
            if wallet_record_id and wallet_record_id != record_id:
                project_events.extend(events_by_record.get(wallet_record_id) or [])
            if chat_id:
                project_events.extend(events_by_chat.get(int(chat_id)) or [])
            project_events.extend(events_by_name.get(name_key) or [])
            digest_date = wallet_first_seen.get(wallet_record_id, "")
            digest_completed = bool(
                wallet_record_id in digested_wallet_ids
                and digest_date
                and digest_date != "baseline"
            )
            digest_event = next(
                (
                    item
                    for item in reversed(indexed_events)
                    if str(item.get("kind") or "") == "wallet_digest_sent"
                    and str(item.get("digest_date") or "") == digest_date
                ),
                None,
            )
            if digest_completed:
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
            qa_evidence = qa_by_chat.get(int(chat_id or 0)) or {
                "replied": 0,
                "silent": 0,
                "last_ts": "",
                "events": [],
            }
            project_events.extend(list(qa_evidence.get("events") or []))

            # De-duplicate evidence reached through multiple indexes.
            unique_events: list[dict[str, Any]] = []
            seen_events: set[tuple[str, str, str]] = set()
            for item in project_events:
                event_key = (
                    str(item.get("kind") or "automation"),
                    str(item.get("ts") or ""),
                    str(item.get("text") or ""),
                )
                if event_key in seen_events:
                    continue
                seen_events.add(event_key)
                unique_events.append(
                    {
                        "kind": event_key[0],
                        "ts": event_key[1],
                        "text": event_key[2] or "自动化任务已执行",
                        "source": str(item.get("source") or "workflow_events"),
                        "status": str(item.get("status") or "success"),
                    }
                )
            unique_events.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)

            def add_unique_event(item: dict[str, Any]) -> None:
                """Add durable workflow evidence when its append-only event is absent."""
                event_key = (
                    str(item.get("kind") or "automation"),
                    str(item.get("ts") or ""),
                    str(item.get("text") or ""),
                )
                if event_key in seen_events:
                    return
                seen_events.add(event_key)
                unique_events.append(
                    {
                        "kind": event_key[0],
                        "ts": event_key[1],
                        "text": event_key[2] or "自动化任务已执行",
                        "source": str(item.get("source") or "workflow_state"),
                        "status": str(item.get("status") or "success"),
                    }
                )

            def latest_event(*kinds: str) -> dict[str, Any] | None:
                wanted = set(kinds)
                return next(
                    (item for item in unique_events if str(item.get("kind")) in wanted),
                    None,
                )

            bound_event = latest_event("folder_chat_added", "welcome_sequence_sent")
            welcome_event = latest_event("welcome_sequence_sent")
            mainnet_event = latest_event("lark_status_changed")
            form_event = latest_event("form_sent")
            logo_event = latest_event("logo_uploaded_lark")
            wallet_digest_event = latest_event("wallet_digest_completed")
            form_sent = record_id in sent_ids or bool(chase_meta)
            form_done = bool(chase_meta.get("done"))
            form_completed_at = chase_meta.get("completed_at")
            logo_status = logo_results.get(record_id, "")
            logo_done = logo_status.startswith("ok") or logo_status == "baseline_has_logo"
            # A project completes the final delivery step only after both
            # prerequisites are true: its Google Form data is complete and its
            # wallet row was included in a successfully sent midnight digest.
            wallet_digest_completed = bool(form_done and digest_completed)
            welcome_done = bool(
                welcome_event or (chat_id and int(chat_id) in greeted_chat_ids)
            )

            # Durable state is still valid evidence when an older run predates
            # the append-only event log. Add it to the same timeline without
            # inventing a timestamp.
            if chat_matches and len(chat_matches) == 1 and not bound_event:
                add_unique_event(
                    {
                        "kind": "folder_chat_added",
                        "text": f"Telegram 群已与 {name} 项目绑定（历史状态无时间）",
                        "source": "Telegram / Lark 绑定状态",
                    }
                )
            if form_sent and not form_event:
                add_unique_event(
                    {
                        "kind": "form_sent",
                        "text": "Google 表单已发送（历史状态无时间）",
                        "ts": chase_meta.get("first_sent_at") or "",
                        "source": "Google 表单状态",
                    }
                )
            if form_done and not latest_event("form_completed"):
                add_unique_event(
                    {
                        "kind": "form_completed",
                        "text": "Google 表单资料已回收（历史状态无时间）",
                        "ts": form_completed_at or "",
                        "source": "Lark 钱包表",
                    }
                )
            if welcome_done and not welcome_event:
                add_unique_event(
                    {
                        "kind": "welcome_sequence_sent",
                        "text": "Bot 自动问候已完成（历史状态无时间）",
                        "source": "Telegram 欢迎状态",
                    }
                )
            if logo_done and not logo_event:
                add_unique_event(
                    {
                        "kind": "logo_uploaded_lark",
                        "text": "项目 Logo 已写入 Lark（历史状态无时间）",
                        "source": "Lark Logo 回填状态",
                    }
                )
            if stage_key == "live" and not mainnet_event:
                add_unique_event(
                    {
                        "kind": "lark_status_changed",
                        "text": "Lark 项目状态为主网上线（历史状态无事件时间）",
                        "ts": event_iso(updated),
                        "source": "Lark 项目状态",
                    }
                )
            unique_events.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
            delivery_steps: list[dict[str, Any]] = []
            if chat_matches:
                delivery_steps.append(
                    step(
                        "group_bound",
                        "BD 建群并绑定项目",
                        "warning" if len(chat_matches) > 1 else "done",
                        (
                            f"找到 {len(chat_matches)} 个 TG 候选群，需管理员确认"
                            if len(chat_matches) > 1
                            else f"Telegram 群已绑定：{chat_title}"
                        ),
                        ts=(bound_event or {}).get("ts"),
                        source="Telegram / Lark",
                    )
                )
            else:
                delivery_steps.append(
                    step(
                        "group_bound",
                        "BD 建群并绑定项目",
                        "pending",
                        "尚未匹配到 Telegram 项目群",
                        source="Telegram / Lark",
                    )
                )

            if chat_id and int(chat_id) in ignored_ids:
                delivery_steps.append(
                    step(
                        "welcome",
                        "Bot 自动问候",
                        "warning",
                        "该群在自动回复黑名单，不发送欢迎消息",
                        source="Telegram",
                    )
                )
            elif welcome_done:
                delivery_steps.append(
                    step(
                        "welcome",
                        "Bot 自动问候",
                        "done",
                        "欢迎消息已发送"
                        + ("" if welcome_event else "（历史状态无时间）"),
                        ts=(welcome_event or {}).get("ts"),
                        source="Telegram",
                    )
                )
            else:
                delivery_steps.append(
                    step(
                        "welcome",
                        "Bot 自动问候",
                        "active" if chat_matches else "pending",
                        "等待 Bot 发送欢迎消息" if chat_matches else "需先绑定 Telegram 群",
                        source="Telegram",
                    )
                )

            replied_count = int(qa_evidence.get("replied") or 0)
            silent_count = int(qa_evidence.get("silent") or 0)
            qa_detail = f"近30天 Bot 已回答 {replied_count} 条"
            if silent_count:
                qa_detail += f"，未自动回复 {silent_count} 条"
            if stage_key in {"live", "main_deploy"}:
                technical_state = "done"
            elif stage_key == "test_deploy" or replied_count:
                technical_state = "active"
            else:
                technical_state = "pending"
            delivery_steps.append(
                step(
                    "technical_support",
                    "生态 App 技术接入",
                    technical_state,
                    qa_detail,
                    ts=qa_evidence.get("last_ts"),
                    source="Telegram 问答日志",
                )
            )

            if stage_key == "live":
                delivery_steps.append(
                    step(
                        "mainnet_live",
                        "主网上线确认",
                        "done",
                        "交付人员已在 Lark 标记主网上线",
                        ts=(mainnet_event or {}).get("ts") or updated,
                        source="Lark 项目状态",
                    )
                )
            else:
                delivery_steps.append(
                    step(
                        "mainnet_live",
                        "主网上线确认",
                        "active" if stage_key == "main_deploy" else "pending",
                        f"Lark 当前状态：{stage_label}",
                        ts=updated,
                        source="Lark 项目状态",
                    )
                )

            delivery_steps.append(
                step(
                    "form_sent",
                    "Google 表单发送",
                    "done" if form_sent else ("active" if stage_key == "live" else "pending"),
                    (
                        "Google 表单已发送至项目群"
                        + ("" if form_event else "（历史状态无时间）")
                        if form_sent
                        else ("已主网上线，等待自动发送" if stage_key == "live" else "主网上线后自动发送")
                    ),
                    ts=(form_event or {}).get("ts") or chase_meta.get("first_sent_at"),
                    source="Google 表单 / Telegram",
                )
            )
            delivery_steps.append(
                step(
                    "form_completed",
                    "Google 表单资料回收",
                    "done" if form_done else ("active" if form_sent else "pending"),
                    (
                        f"项目资料已回收，已填 {int(chase_meta.get('filled_count') or 0)} 个字段"
                        if form_done
                        else ("表单已发送，等待资料齐全" if form_sent else "表单发送后开始跟踪")
                    ),
                    ts=form_completed_at,
                    source="Lark 钱包表",
                )
            )
            delivery_steps.append(
                step(
                    "logo_uploaded",
                    "项目 Logo 回填",
                    "done" if logo_done else ("warning" if logo_status else "pending"),
                    (
                        "Logo 已写入 Lark"
                        + ("" if logo_event else "（历史状态无时间）")
                        if logo_done
                        else (f"Logo 处理结果：{logo_status}" if logo_status else "尚无 Logo 回填记录")
                    ),
                    ts=(logo_event or {}).get("ts"),
                    source="Lark Logo 回填",
                )
            )
            delivery_steps.append(
                step(
                    "wallet_digest",
                    "钱包地址日报",
                    "done" if wallet_digest_completed else ("active" if form_done else "pending"),
                    (
                        "钱包地址已纳入午夜日报"
                        + ("" if wallet_digest_event else "（历史状态无时间）")
                        if wallet_digest_completed
                        else (
                            "表单资料已回收，等待下一次午夜日报"
                            if form_done
                            else "Google 表单资料回收后，将在午夜日报发送后完成"
                        )
                    ),
                    ts=(wallet_digest_event or {}).get("ts"),
                    source="Lark 钱包地址日报",
                )
            )

            issues: list[dict[str, str]] = []
            if not chat_matches:
                issues.append({"level": "high", "text": "未匹配到 Telegram 项目群"})
            elif len(chat_matches) > 1:
                issues.append({"level": "medium", "text": f"TG 绑定有 {len(chat_matches)} 个候选群，需要确认"})
            if stage_key == "live" and not form_sent:
                issues.append({"level": "medium", "text": "已主网上线，但 Google 表单尚未发送"})
            if form_sent and not form_done:
                issues.append({"level": "low", "text": "等待项目方补齐表单资料"})
            if form_done and not wallet_digest_completed:
                issues.append({"level": "medium", "text": "表单资料已回收，等待下一次午夜钱包地址日报"})

            rows.append(
                {
                    "record_id": record_id,
                    "project": name[:160],
                    "stage": stage_key,
                    "stage_label": stage_label[:120],
                    "status_raw": status_raw[:200],
                    "bd": bd[:120],
                    "delivery": delivery[:120],
                    "updated_at": updated,
                    "chat_id": chat_id,
                    "chat_title": chat_title[:160],
                    "tg_bound": bool(chat_matches),
                    "tg_ambiguous": len(chat_matches) > 1,
                    "tg_match_count": len(chat_matches),
                    "tg_match_candidates": [
                        {
                            "chat_id": item[0],
                            "chat_title": item[1][:160],
                            "score": item[2],
                            "reason": item[3],
                        }
                        for item in chat_matches[:8]
                    ],
                    "tg_ignored": any(item[0] in ignored_ids for item in chat_matches),
                    "tg_match_reason": match_reason,
                    "lark_bound": True,
                    "form_sent": form_sent,
                    "form_completed": form_done,
                    "wallet_record_id": wallet_record_id,
                    "wallet_fields_present": sum(
                        1
                        for value in wallet_fields.values()
                        if _field_text({"value": value}, "value")
                    ),
                    "wallet_digest_completed": wallet_digest_completed,
                    # Compatibility alias for older dashboard consumers.
                    "department_notified": wallet_digest_completed,
                    "logo_status": logo_status,
                    "delivery_steps": delivery_steps,
                    "project_events": unique_events[:30],
                    "issues": issues,
                }
            )

        order = {"main_deploy": 0, "test_deploy": 1, "other": 2, "live": 3}
        rows.sort(key=lambda row: (order.get(str(row.get("stage")), 9), str(row.get("project") or "").lower()))
        known_statuses = {str(item.get("name") or "") for item in status_options}
        for row in rows:
            raw_status = str(row.get("status_raw") or "").strip()
            if raw_status and raw_status not in known_statuses:
                status_options.append(
                    {
                        "id": "",
                        "name": raw_status,
                        "color": None,
                        "source": "lark_record",
                    }
                )
                known_statuses.add(raw_status)
        out["status_options"] = status_options
        out["total"] = len(rows)
        out["matched"] = sum(1 for row in rows if row.get("tg_bound"))
        out["matched_unique"] = sum(
            1 for row in rows if row.get("tg_bound") and not row.get("tg_ambiguous")
        )
        out["ambiguous"] = sum(1 for row in rows if row.get("tg_ambiguous"))
        out["form_pending"] = sum(
            1 for row in rows if row.get("stage") == "live" and not row.get("form_sent")
        )
        out["rows"] = rows
    except Exception as exc:  # noqa: BLE001
        logger.exception("dashboard: live project rows failed")
        out["error"] = str(exc)
    return out


def _dashboard_path(config: Any, attr: str, default: str) -> Path:
    raw = str(getattr(config, attr, default) or default)
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _event_datetime(value: Any) -> datetime | None:
    """Parse an ISO timestamp or Unix seconds/milliseconds for dashboard feeds."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            number = float(value)
            if number > 10_000_000_000:
                number /= 1000
            return datetime.fromtimestamp(number, TZ)
        except (OverflowError, OSError, ValueError):
            return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def _read_jsonl(path: Path, *, max_days: int = 30) -> list[dict[str, Any]]:
    """Read bounded JSONL rows, ignoring malformed or very old records."""
    if not path.is_file():
        return []
    since = datetime.now(TZ) - timedelta(days=max(int(max_days), 1))
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                ts = _event_datetime(row.get("ts"))
                if ts is not None and ts < since:
                    continue
                rows.append(row)
    except OSError:
        logger.exception("dashboard: failed reading event log %s", path)
    return rows


def _short_workflow_status(status: str) -> str:
    text = str(status or "").strip()
    if not text:
        return "未设置"
    if "主网上线" in text:
        return "主网上线"
    if "主网部署" in text:
        return "主网部署中"
    if "测试网部署" in text:
        return "测试网部署"
    return text[:60]


def _build_recent_workflow_activities(
    config: Any,
    *,
    qa: dict[str, Any] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build named activity rows only from persisted, timestamped evidence."""
    activities: list[dict[str, Any]] = []
    for item in (qa or {}).get("answered") or []:
        ts = _event_datetime(item.get("ts"))
        if ts is None:
            continue
        chat = str(item.get("chat_title") or "Telegram 群")[:120]
        activities.append(
            {
                "ts": ts.isoformat(timespec="seconds"),
                "icon": "message-square-reply",
                "kind": "qa",
                "project": chat,
                "text": f"Bot 在 {chat} 回复了一条消息",
                "source": "message_logs",
            }
        )

    # Shared append-only event feed for automation actions that do not have a
    # dedicated state file (welcome, folder auto-add, webhook, notifications,
    # digest sends, failures, etc.). Wallet/form events are also represented by
    # their dedicated state readers below, so skip those kinds here to avoid
    # duplicate rows.
    workflow_events_path = _dashboard_path(
        config, "workflow_events_file", "data/workflow_events.jsonl"
    )
    dedicated_kinds = {
        "wallet_collected",
        "form_sent",
        "form_chase_reminder",
        # Logo events are rendered below from their dedicated detail log.
        "logo_uploaded_lark",
    }
    seen_skip_events: set[tuple[str, str, str]] = set()
    # Read newest-first so legacy retry spam collapses to the latest visible row.
    for item in reversed(_read_jsonl(workflow_events_path)):
        kind = str(item.get("kind") or "automation")
        if kind in dedicated_kinds:
            continue
        if kind == "form_dispatch_skipped":
            skip_key = (
                kind,
                str(item.get("record_id") or item.get("project_name") or ""),
                str(item.get("reason") or ""),
            )
            if skip_key in seen_skip_events:
                continue
            seen_skip_events.add(skip_key)
        ts = _event_datetime(item.get("ts"))
        if ts is None:
            continue
        name = str(item.get("project_name") or item.get("chat_title") or "系统")[:120]
        status = str(item.get("status") or "success").lower()
        icon = str(item.get("icon") or "workflow")
        if status in {"error", "failed", "fail"}:
            icon = "circle-x"
        text = str(item.get("text") or "自动化任务已执行")[:240]
        activities.append(
            {
                "ts": ts.isoformat(timespec="seconds"),
                "icon": icon,
                "kind": kind,
                "project": name,
                "text": text,
                "source": str(item.get("source") or "workflow_events"),
                "status": status,
            }
        )

    logo_path = _dashboard_path(
        config, "workflow_logo_events_file", "data/logo_fill_events.jsonl"
    )
    for item in _read_jsonl(logo_path):
        ts = _event_datetime(item.get("ts"))
        if ts is None:
            continue
        name = str(item.get("project_name") or item.get("record_id") or "未命名项目")[:120]
        status = str(item.get("status") or "")
        if status.startswith("ok"):
            icon, text = "image", f"{name} 的 Logo 已写入 Lark"
        elif status.startswith(("err", "fail")):
            icon, text = "image-off", f"{name} 的 Logo 抓取失败"
        elif status in {"no_logo", "no_url"}:
            icon, text = "image-off", f"{name} 未找到可用 Logo"
        else:
            continue
        activities.append(
            {
                "ts": ts.isoformat(timespec="seconds"),
                "icon": icon,
                "kind": "logo",
                "project": name,
                "text": text,
                "source": "logo_fill_events",
            }
        )

    for item in _read_jsonl(workflow_events_path):
        if str(item.get("kind") or "") != "wallet_collected":
            continue
        ts = _event_datetime(item.get("ts"))
        if ts is None:
            continue
        name = str(item.get("project_name") or item.get("record_id") or "未命名项目")[:120]
        address_count = int(item.get("address_count") or 0)
        count_text = f"{address_count} 个地址字段" if address_count else "钱包地址"
        activities.append(
            {
                "ts": ts.isoformat(timespec="seconds"),
                "icon": "wallet",
                "kind": "wallet",
                "project": name,
                "text": f"{name} 的钱包地址已自动收集到 Lark（{count_text}）",
                "source": "lark_wallet_table",
                "status": "success",
            }
        )

    deploy_path = _dashboard_path(
        config,
        "workflow_deploy_status_watch_state_file",
        "data/deploy_status_watch_state.json",
    )
    deploy_state: dict[str, Any] = {}
    if deploy_path.is_file():
        try:
            raw = json.loads(deploy_path.read_text(encoding="utf-8"))
            deploy_state = raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            deploy_state = {}
    for item in deploy_state.get("events") or []:
        if not isinstance(item, dict):
            continue
        ts = _event_datetime(item.get("ts"))
        if ts is None:
            continue
        name = str(item.get("name") or item.get("record_id") or "未命名项目")[:120]
        new_status = _short_workflow_status(str(item.get("to") or ""))
        activities.append(
            {
                "ts": ts.isoformat(timespec="seconds"),
                "icon": "git-branch",
                "kind": "status",
                "project": name,
                "text": f"{name} 状态更新为 {new_status}",
                "source": "deploy_status_watch",
            }
        )

    chase_path = _dashboard_path(
        config, "workflow_form_chase_state_file", "data/form_chase_state.json"
    )
    if chase_path.is_file():
        try:
            raw = json.loads(chase_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        for record in (raw.get("projects") or {}).values() if isinstance(raw, dict) else []:
            if not isinstance(record, dict):
                continue
            name = str(record.get("project_name") or "未命名项目")[:120]
            first = _event_datetime(record.get("first_sent_at"))
            if first is not None:
                activities.append(
                    {
                        "ts": first.isoformat(timespec="seconds"),
                        "icon": "file-check-2",
                        "kind": "form",
                        "project": name,
                        "text": f"{name} 的 Google 表单已发送",
                        "source": "form_chase_state",
                    }
                )
            reminders = int(record.get("reminders_sent") or 0)
            last = _event_datetime(record.get("last_sent_at"))
            if reminders > 0 and last is not None and last != first:
                activities.append(
                    {
                        "ts": last.isoformat(timespec="seconds"),
                        "icon": "bell-ring",
                        "kind": "form",
                        "project": name,
                        "text": f"{name} 的表单催收已发送（第 {reminders} 次）",
                        "source": "form_chase_state",
                    }
                )

    activities.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    return activities[:20]


def _task_counter(snapshot: dict[str, Any], key: str, field: str = "today") -> int:
    counters = snapshot.get("counters") or {}
    return int((counters.get(key) or {}).get(field) or 0)


def _task_rate(ok: int, total: int) -> str:
    if total <= 0:
        return "—"
    return f"{(ok / total * 100):.1f}%"


def build_automation_tasks(
    config: Any,
    snapshot_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Expose every configured automation component with real counters."""
    payload = snapshot_payload or {}
    snap = payload.get("snapshot") or {}
    counters = snap.get("counters") or {}
    qa = payload.get("qa") or {}
    today_events = _task_counter

    def task(
        key: str,
        label: str,
        description: str,
        icon: str,
        enabled: bool,
        today: int,
        *,
        success_rate: str = "—",
        mode: str = "事件触发",
        status: str | None = None,
        detail: str = "",
    ) -> dict[str, Any]:
        running = bool(enabled)
        return {
            "key": key,
            "label": label,
            "description": description,
            "icon": icon,
            "enabled": running,
            "status": status or ("运行中" if running else "已关闭"),
            "today": int(today),
            "success_rate": success_rate,
            "mode": mode,
            "detail": detail,
        }

    processed = today_events(snap, "messages_processed")
    faq = today_events(snap, "faq_reply_sessions")
    sent = today_events(snap, "messages_sent")
    form_ok = today_events(snap, "form_dispatch_success")
    form_fail = today_events(snap, "form_dispatch_fail")
    form_skip = today_events(snap, "form_dispatch_skip")
    logo_ok = today_events(snap, "logo_fill_success")
    logo_fail = today_events(snap, "logo_fill_fail")
    webhook_in = today_events(snap, "webhook_live_received")
    webhook_done = today_events(snap, "webhook_live_processed")
    welcome = today_events(snap, "welcome_sequences_started")
    folder = today_events(snap, "folder_auto_add_success")
    wallet_new = today_events(snap, "wallet_digest_new_projects")
    event_rows = _read_jsonl(
        _dashboard_path(config, "workflow_events_file", "data/workflow_events.jsonl")
    )
    chase_today = sum(1 for row in event_rows if row.get("kind") == "form_chase_reminder")
    lark_sync = today_events(snap, "agent_kb_lark_sync_success")
    deploy_changes = today_events(snap, "deploy_status_transitions")

    tasks = [
        task("folder_add", "项目群自动归档", "将新项目群加入 Telegram 文件夹", "folder-plus", bool(getattr(config, "folder_auto_add_enabled", False)), folder, mode=f"每 {getattr(config, 'folder_auto_add_scan_minutes', 15)} 分钟扫描", detail="新增归档群数"),
        task("welcome", "新群自动问候", "新加入项目群发送欢迎序列", "hand-heart", bool(getattr(config, "welcome_enabled", False)), welcome, mode=f"每 {getattr(config, 'welcome_scan_interval_minutes', 15)} 分钟扫描", detail="启动序列计数"),
        task("tg_qa", "交付 Bot 问答", "TG 群自动回答与人工纠错", "message-circle", bool(getattr(config, "group_replies_enabled", False)), processed, success_rate=_task_rate(faq, processed), mode="实时监听", detail=f"已处理 {processed} 条入站"),
        task("lark_sync", "Lark 知识库同步", "同步项目知识与 Agent 检索库", "refresh-cw", bool(getattr(config, "lark_sync_enabled", False)), lark_sync, mode=f"每 {getattr(config, 'lark_sync_interval_minutes', 60)} 分钟", detail="来自 Lark 同步成功计数"),
        task("live_webhook", "主网上线 Webhook", "接收 Lark 状态变更并触发交付", "webhook", bool(getattr(config, "workflow_live_webhook_enabled", False)), webhook_done, success_rate=_task_rate(webhook_done, webhook_in), mode="Webhook 实时", detail=f"收到 {webhook_in} · 已处理 {webhook_done}"),
        task("status_watch", "Lark 状态监听", "监听主网与测试网部署状态变化", "radio", bool(getattr(config, "workflow_live_status_watch_enabled", False) or getattr(config, "workflow_deploy_status_watch_enabled", False)), deploy_changes, mode=f"每 {getattr(config, 'workflow_live_status_watch_seconds', 60)} 秒", detail="状态变更计数"),
        task("form_dispatch", "Google 表单发送", "主网上线后向项目群发送表单", "file-check-2", bool(getattr(config, "workflow_enabled", False) and getattr(config, "workflow_google_form_url", "")), form_ok, success_rate=_task_rate(form_ok, form_ok + form_fail), mode="状态触发 / 轮询", detail=f"成功 {form_ok} · 跳过 {form_skip} · 失败 {form_fail}"),
        task("form_chase", "表单自动催收", "按缺失字段向项目群发送提醒", "bell-ring", bool(getattr(config, "workflow_form_chase_enabled", False)), chase_today, mode=f"每 {getattr(config, 'workflow_form_chase_scan_minutes', 60)} 分钟", detail="今日催收事件"),
        task("logo_fill", "Logo 自动回填", "抓取官网 Logo 并写入 Lark", "image", bool(getattr(config, "workflow_logo_fill_enabled", False)), logo_ok, success_rate=_task_rate(logo_ok, logo_ok + logo_fail), mode="状态触发 / 轮询", detail=f"成功 {logo_ok} · 失败 {logo_fail}"),
        task("wallet_digest", "钱包地址日报", "收集钱包资料并发送 Lark 摘要", "wallet-cards", bool(getattr(config, "workflow_lark_digest_enabled", False)), wallet_new, mode=f"每日 {getattr(config, 'workflow_lark_digest_hour', 0):02d}:00", detail="今日新钱包项目"),
        task("metrics", "消息指标与真实日志", "记录 TG 入站、回答和沉默原因", "chart-no-axes-combined", bool(getattr(config, "metrics_enabled", False) and getattr(config, "metrics_message_log_enabled", False)), int((qa.get("counts") or {}).get("lines") or 0), mode="实时写入", detail="消息日志扫描行数"),
        task("dashboard", "看板快照刷新", "生成跨平台实时看板数据", "layout-dashboard", bool(getattr(config, "dashboard_enabled", False)), 1, mode=f"每 {getattr(config, 'dashboard_refresh_minutes', 60)} 分钟", detail=f"最近更新 {payload.get('generated_at') or '—'}"),
    ]
    enabled = sum(1 for item in tasks if item["enabled"])
    failures = form_fail + logo_fail
    return {
        "total": len(tasks),
        "enabled": enabled,
        "today_executions": sum(int(item["today"]) for item in tasks),
        "failures": failures,
        "retries": None,
        "avg_duration": None,
        "tasks": tasks,
    }


def build_workflow_overview(
    config: Any,
    projects: dict[str, Any] | None,
    snapshot_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return real funnel, recent activities, and actionable exceptions."""
    projects = projects or {}
    snapshot_payload = snapshot_payload or {}
    rows = [row for row in (projects.get("rows") or []) if isinstance(row, dict)]
    snap = snapshot_payload.get("snapshot") or {}
    derived = snap.get("derived") or {}
    qa = snapshot_payload.get("qa") or {}
    live_rows = [row for row in rows if row.get("stage") == "live"]
    main_rows = [row for row in rows if row.get("stage") == "main_deploy"]
    test_rows = [row for row in rows if row.get("stage") == "test_deploy"]
    form_pending_rows = [row for row in live_rows if not row.get("form_sent")]
    wallet = snap.get("wallet_lark") or {}
    wallet_total = wallet.get("total_rows")
    wallet_with_address = wallet.get("projects_with_any_address")
    wallet_incomplete = None
    if wallet_total is not None and wallet_with_address is not None:
        wallet_incomplete = max(0, int(wallet_total) - int(wallet_with_address))

    technical_rows = [
        row
        for row in rows
        if row.get("stage") == "test_deploy"
        or any(token in str(row.get("status_raw") or "") for token in ("接入", "对接"))
    ]
    wallet_digest_completed = sum(
        1 for row in rows if bool(row.get("wallet_digest_completed"))
    )
    logo_state = derived.get("logo_fill_state") or {}
    logo_fail = int(logo_state.get("fail") or 0)

    steps = [
        {
            "key": "bound",
            "label": "TG / Lark 已绑定",
            "count": int(projects.get("matched") or 0),
            "note": f"共 {len(rows)} 条 Lark 项目记录",
        },
        {
            "key": "technical",
            "label": "技术接入中",
            "count": len(technical_rows),
            "note": "按 Lark 项目状态统计",
        },
        {
            "key": "main_deploy",
            "label": "主网部署中",
            "count": len(main_rows),
            "note": "当前状态为主网部署中",
        },
        {
            "key": "form_pending",
            "label": "上线后待回收表单",
            "count": len(form_pending_rows),
            "note": "主网上线且尚未标记表单已发送",
        },
        {
            "key": "wallet_incomplete",
            "label": "钱包地址待补齐",
            "count": wallet_incomplete,
            "note": "来自 Lark 钱包表",
        },
        {
            "key": "notified",
            "label": "钱包地址日报已完成",
            "count": wallet_digest_completed,
            "note": "表单已回收且已纳入午夜日报的项目",
        },
    ]

    exceptions: list[dict[str, Any]] = []
    if projects.get("error"):
        exceptions.append(
            {
                "severity": "high",
                "icon": "triangle-alert",
                "title": "Lark 项目数据读取失败",
                "meta": str(projects.get("error"))[:240],
                "project": "",
                "action": None,
                "source": "dashboard_api",
            }
        )
    for row in rows:
        if row.get("tg_bound"):
            continue
        reason = str(row.get("tg_match_reason") or "未找到群标题匹配")
        exceptions.append(
            {
                "severity": "high" if "ambiguous" in reason else "medium",
                "icon": "link-2-off",
                "title": "TG / Lark 未完成绑定",
                "meta": f"{row.get('project') or row.get('record_id') or '未命名项目'} · {reason}",
                "project": row.get("project") or "",
                "action": None,
                "source": "project_matching",
            }
        )
    for row in form_pending_rows:
        exceptions.append(
            {
                "severity": "high",
                "icon": "file-clock",
                "title": "主网上线后待发送表单",
                "meta": f"{row.get('project') or row.get('record_id') or '未命名项目'} · Lark 状态为主网上线",
                "project": row.get("project") or "",
                "action": None,
                "source": "form_dispatch",
            }
        )
    for row in (qa.get("silent") or [])[:20]:
        chat = str(row.get("chat_title") or "Telegram 群")
        reason = str(row.get("reason") or "未分类")
        exceptions.append(
            {
                "severity": "medium",
                "icon": "message-circle-question",
                "title": "Bot 未自动回复，待人工判断",
                "meta": f"{chat} · {reason[:160]}",
                "project": chat,
                "action": None,
                "source": "message_logs",
            }
        )
    if logo_fail:
        exceptions.append(
            {
                "severity": "medium",
                "icon": "image-off",
                "title": "Logo 抓取失败",
                "meta": f"当前 Logo 状态文件记录失败 {logo_fail} 条",
                "project": "",
                "action": None,
                "source": "logo_state",
            }
        )
    severity_order = {"high": 0, "medium": 1, "low": 2}
    exceptions.sort(key=lambda item: severity_order.get(str(item.get("severity")), 9))

    activities = _build_recent_workflow_activities(config, qa=qa, rows=rows)
    return {
        "generated_at": _now_iso(),
        "funnel": {
            "total": len(rows),
            "live": len(live_rows),
            "test_deploy": len(test_rows),
            "steps": steps,
        },
        "activities": activities,
        "activities_empty": not activities,
        "exceptions": exceptions[:50],
        "exceptions_total": len(exceptions),
        "exceptions_visible": min(len(exceptions), 5),
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
