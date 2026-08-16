"""Build / load Delivery Agent dashboard snapshot (hourly, disk-backed)."""

from __future__ import annotations

import json
import logging
import os
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
    series = _counter_series(config)
    calendar = build_calendar_activity(config, days=calendar_days)
    ranges = {
        "7": build_range_summary(config, 7, series=series, list_limit=limit),
        "30": build_range_summary(config, 30, series=series, list_limit=limit),
    }

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
        "rows": [],
        "error": None,
    }
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        out["error"] = "missing LARK credentials"
        return out

    try:
        from bot.lark_bitable import get_tenant_access_token, list_records
        from bot.workflow_form_dispatch import _field_text, match_project_to_chat

        token = get_tenant_access_token(app_id, app_secret)
        records = list_records(
            token,
            str(getattr(config, "workflow_base_app_token", "")),
            str(getattr(config, "workflow_progress_table_id", "")),
        )

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

        status_field = str(getattr(config, "workflow_status_field", "项目状态") or "项目状态")
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
            chat_id, match_reason = match_project_to_chat(name, title_cache)
            chat_title = title_cache.get(chat_id) if chat_id is not None else ""
            bd = _field_text(fields, bd_field)
            delivery = _field_text(fields, delivery_field)
            updated = fields.get(update_field)
            rows.append(
                {
                    "record_id": str(record.get("record_id") or ""),
                    "project": name[:160],
                    "stage": stage_key,
                    "stage_label": stage_label[:120],
                    "status_raw": status_raw[:200],
                    "bd": bd[:120],
                    "delivery": delivery[:120],
                    "updated_at": updated,
                    "chat_id": chat_id,
                    "chat_title": chat_title[:160],
                    "tg_bound": chat_id is not None,
                    "tg_ignored": chat_id in ignored_ids if chat_id is not None else False,
                    "tg_match_reason": match_reason,
                    "lark_bound": True,
                }
            )

        order = {"main_deploy": 0, "test_deploy": 1, "other": 2, "live": 3}
        rows.sort(key=lambda row: (order.get(str(row.get("stage")), 9), str(row.get("project") or "").lower()))
        sent_ids: set[str] = set()
        state_raw = str(getattr(config, "workflow_state_file", "data/form_dispatch_state.json") or "data/form_dispatch_state.json")
        state_path = Path(state_raw)
        if not state_path.is_absolute():
            state_path = ROOT / state_path
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                sent_ids = {str(item) for item in (state.get("sent_record_ids") or [])}
            except (OSError, json.JSONDecodeError, TypeError):
                sent_ids = set()
        for row in rows:
            row["form_sent"] = row.get("record_id") in sent_ids
        out["total"] = len(rows)
        out["matched"] = sum(1 for row in rows if row.get("tg_bound"))
        out["form_pending"] = sum(
            1 for row in rows if row.get("stage") == "live" and not row.get("form_sent")
        )
        out["rows"] = rows
    except Exception as exc:  # noqa: BLE001
        logger.exception("dashboard: live project rows failed")
        out["error"] = str(exc)
    return out


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
