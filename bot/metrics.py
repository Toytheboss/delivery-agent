"""Delivery automation metrics: counters + derived snapshot.

FAQ metric choice
-----------------
``faq_reply_sessions`` counts one successful FAQ auto-reply session (after all
bubbles for that question are sent), not individual bubbles. Footer messages
are counted separately as ``faq_footer_sent``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone
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

_lock = threading.RLock()
_enabled = True
_state_path = ROOT / "data" / "delivery_metrics.json"
_data: dict[str, Any] | None = None

# Live counter keys (total + by_day Asia/Shanghai)
COUNTER_KEYS = (
    "faq_reply_sessions",
    "human_review_alerts",
    "faq_bubbles_sent",
    "faq_footer_sent",
    "messages_processed",
    "messages_sent",
    "welcome_sequences_started",
    "welcome_messages_sent",
    "folder_auto_add_success",
    "form_dispatch_success",
    "form_dispatch_skip",
    "form_dispatch_fail",
    "logo_fill_success",
    "logo_fill_fail",
    "logo_fill_no_logo",
    "mark_live_triggers",
    "mark_live_resolve",
    "send_form_triggers",
    "absorb_learn_success",
    "agent_kb_lark_sync_success",
    "wallet_digest_new_projects",
    "wallet_digest_sent",
    "webhook_live_received",
    "webhook_live_processed",
    "poll_cycles_run",
    "deploy_status_transitions",
    "social_chitchat_replies",
)


_HOURLY_RETAIN_HOURS = 8 * 24


def _today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def _hour_key(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%dT%H")


def _now() -> datetime:
    return datetime.now(TZ)


def _window_start(*, hours: int) -> datetime:
    return _now() - timedelta(hours=hours)


def _dates_covering_hours(hours: int) -> list[str]:
    """Calendar days (Asia/Shanghai) that intersect [now-hours, now], oldest first.

    Metric counters are day-bucketed; this is the practical window for
    ``过去24小时`` / ``过去7天`` without hourly buckets.
    """
    end = _now()
    start = end - timedelta(hours=max(int(hours), 1))
    days: list[str] = []
    cursor = start.date()
    last = end.date()
    while cursor <= last:
        days.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return days


def _week_dates(n: int = 7) -> list[str]:
    """Past n×24 hours, as calendar days covering that rolling window."""
    return _dates_covering_hours(max(int(n), 1) * 24)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_iso_ts(value: Any) -> datetime | None:
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


def _ms_to_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, TZ)
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _judge_datetime(value: Any) -> datetime | None:
    """Lark written-time: ms, seconds, ISO text, or wrapped option."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=TZ)
        return value.astimezone(TZ)
    if isinstance(value, list) and value:
        return _judge_datetime(value[0])
    if isinstance(value, dict):
        return _judge_datetime(
            value.get("value") or value.get("text") or value.get("name")
        )
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        if n > 1_000_000_000_000:
            n /= 1000.0
        elif n < 1_000_000_000:
            return None
        try:
            return datetime.fromtimestamp(n, TZ)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    parsed = _parse_iso_ts(text)
    if parsed is None and " " in text[:19]:
        parsed = _parse_iso_ts(text.replace(" ", "T", 1))
    if parsed is not None:
        return parsed
    return _ms_to_datetime(text)


def _in_time_window(dt: datetime | None, *, since: datetime) -> bool:
    return dt is not None and dt >= since


def _empty_counter() -> dict[str, Any]:
    return {"total": 0, "by_day": {}, "by_hour": {}}


def _default_data() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": "",
        "counters": {k: _empty_counter() for k in COUNTER_KEYS},
        "notes": {
            "faq_unit": "reply_session",
            "timezone": "Asia/Shanghai",
        },
    }


def configure(*, enabled: bool = True, state_file: str | Path | None = None) -> None:
    """Apply config (call once at startup)."""
    global _enabled, _state_path, _data
    with _lock:
        _enabled = bool(enabled)
        if state_file:
            path = Path(state_file)
            _state_path = path if path.is_absolute() else ROOT / path
        _data = None  # reload on next use


def is_enabled() -> bool:
    return _enabled


def _ensure_loaded() -> dict[str, Any]:
    global _data
    if _data is not None:
        return _data
    data = _default_data()
    if _state_path.exists():
        try:
            raw = json.loads(_state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                counters = raw.get("counters") or {}
                for key in COUNTER_KEYS:
                    src = counters.get(key) or {}
                    total = int(src.get("total") or 0)
                    by_day = {
                        str(d): int(n)
                        for d, n in (src.get("by_day") or {}).items()
                    }
                    by_hour = {
                        str(h): int(n)
                        for h, n in (src.get("by_hour") or {}).items()
                    }
                    data["counters"][key] = {
                        "total": total,
                        "by_day": by_day,
                        "by_hour": by_hour,
                    }
                data["updated_at"] = str(raw.get("updated_at") or "")
                if isinstance(raw.get("notes"), dict):
                    data["notes"].update(raw["notes"])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.exception("metrics: failed to load %s; starting fresh", _state_path)
    # Hourly windows are exact only for periods that start after this moment.
    data["notes"].setdefault("hourly_since", _now_iso())
    _data = data
    return _data


def _save_unlocked() -> None:
    if _data is None:
        return
    _data["updated_at"] = _now_iso()
    try:
        _state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = _state_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(_state_path)
    except OSError:
        logger.exception("metrics: failed to save %s", _state_path)


def inc(key: str, n: int = 1) -> None:
    """Increment a counter (total + today's Asia/Shanghai day bucket)."""
    if not _enabled or n == 0:
        return
    if key not in COUNTER_KEYS:
        logger.debug("metrics: unknown key %r ignored", key)
        return
    with _lock:
        data = _ensure_loaded()
        bucket = data["counters"].setdefault(key, _empty_counter())
        bucket["total"] = int(bucket.get("total") or 0) + n
        now = _now()
        day = now.strftime("%Y-%m-%d")
        by_day = bucket.setdefault("by_day", {})
        by_day[day] = int(by_day.get(day) or 0) + n
        # Keep by_day bounded (~90 days)
        if len(by_day) > 100:
            for old in sorted(by_day.keys())[:-90]:
                by_day.pop(old, None)
        hour = _hour_key(now)
        by_hour = bucket.setdefault("by_hour", {})
        by_hour[hour] = int(by_hour.get(hour) or 0) + n
        cutoff = _hour_key(now - timedelta(hours=_HOURLY_RETAIN_HOURS))
        for old in [h for h in by_hour if h < cutoff]:
            by_hour.pop(old, None)
        _save_unlocked()


def get_counter(key: str) -> dict[str, int]:
    with _lock:
        data = _ensure_loaded()
        c = data["counters"].get(key) or _empty_counter()
        today = _today()
        return {
            "total": int(c.get("total") or 0),
            "today": int((c.get("by_day") or {}).get(today) or 0),
        }


def get_counter_series(keys: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    """Return {key: {total, by_day}} for chart series (includes full by_day maps)."""
    want = tuple(keys) if keys is not None else COUNTER_KEYS
    out: dict[str, Any] = {}
    with _lock:
        data = _ensure_loaded()
        for key in want:
            c = data["counters"].get(key) or _empty_counter()
            by_day = {
                str(d): int(n or 0)
                for d, n in (c.get("by_day") or {}).items()
                if d
            }
            out[str(key)] = {
                "total": int(c.get("total") or 0),
                "by_day": by_day,
            }
    return out


def _sum_days(by_day: dict[str, Any] | None, days: list[str]) -> int:
    raw = by_day or {}
    return sum(int(raw.get(d) or 0) for d in days)


def _hourly_since() -> datetime | None:
    with _lock:
        notes = _ensure_loaded().get("notes") or {}
    return _parse_iso_ts(notes.get("hourly_since"))


def _window_count(
    bucket: dict[str, Any] | None,
    *,
    since: datetime,
    day_days: list[str],
    hourly_since: datetime | None,
) -> tuple[int, bool]:
    """Counter value inside [since, now]; second item is True when hour-exact.

    Hour buckets are used when they cover the whole window; otherwise this
    falls back to the calendar days that intersect the window.
    """
    bucket = bucket or {}
    oldest_kept = _now() - timedelta(hours=_HOURLY_RETAIN_HOURS)
    if hourly_since is not None and hourly_since <= since and since >= oldest_kept:
        start_key = _hour_key(since.replace(minute=0, second=0, microsecond=0))
        by_hour = bucket.get("by_hour") or {}
        return sum(int(n or 0) for h, n in by_hour.items() if h >= start_key), True
    return _sum_days(bucket.get("by_day") or {}, day_days), False


def _counter_triple(
    counters_raw: dict[str, Any],
    key: str,
    week_days: list[str],
    *,
    day_days: list[str] | None = None,
) -> dict[str, int]:
    """Return total / past-7d / past-24h (keys kept as week/today for compat)."""
    c = counters_raw.get(key) or _empty_counter()
    by_day = c.get("by_day") or {}
    last_24h_days = day_days if day_days is not None else _dates_covering_hours(24)
    return {
        "total": int(c.get("total") or 0),
        "week": _sum_days(by_day, week_days),
        "today": _sum_days(by_day, last_24h_days),
    }


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _derived_from_state(config: Any) -> dict[str, Any]:
    root = ROOT
    form_path = root / str(
        getattr(config, "workflow_state_file", "data/form_dispatch_state.json")
    )
    logo_path = root / str(
        getattr(config, "workflow_logo_state_file", "data/logo_fill_state.json")
    )
    welcome_path = root / str(
        getattr(config, "welcome_state_file", "data/group_welcome_state.json")
    )
    digest_path = root / str(
        getattr(
            config,
            "workflow_lark_digest_state_file",
            "data/lark_wallet_digest_state.json",
        )
    )

    form_raw = _safe_json(form_path)
    form_sent = form_raw.get("sent_record_ids") or []
    form_processed = len(form_sent)

    logo_raw = _safe_json(logo_path)
    logo_results = logo_raw.get("results") or {}
    logo_success = logo_fail = logo_no_logo = logo_other = 0
    for status in logo_results.values():
        s = str(status)
        if s.startswith("ok"):
            logo_success += 1
        elif s in {"no_logo", "no_url"}:
            logo_no_logo += 1
        elif s.startswith("err") or s.startswith("fail"):
            logo_fail += 1
        else:
            logo_other += 1

    welcome_raw = _safe_json(welcome_path)
    greeted = welcome_raw.get("greeted_chat_ids") or []
    pending = welcome_raw.get("pending_chat_ids") or []

    digest_raw = _safe_json(digest_path)
    first_seen = digest_raw.get("first_seen") or {}
    today = _today()
    digest_new_today = sum(1 for day in first_seen.values() if day == today)

    knowledge_dir = getattr(config, "knowledge_dir", root / "knowledge")
    sub = str(getattr(config, "learn_subdirectory", "learned") or "learned")
    learned_dir = Path(knowledge_dir) / sub
    learned_count = (
        len(list(learned_dir.glob("learned_*.md"))) if learned_dir.is_dir() else 0
    )

    return {
        "form_dispatch_processed": form_processed,
        "logo_fill_state": {
            "processed": len(logo_raw.get("processed_record_ids") or []),
            "success": logo_success,
            "fail": logo_fail,
            "no_logo": logo_no_logo,
            "other": logo_other,
        },
        "welcome_greeted_count": len(greeted),
        "welcome_pending_count": len(pending),
        "learned_md_count": learned_count,
        "wallet_digest_new_today_from_state": digest_new_today,
        "wallet_digest_last_date": str(digest_raw.get("last_digest_date") or ""),
    }


def _wallet_table_counts(config: Any) -> dict[str, Any]:
    """Query Lark wallet table: projects with name + address coverage."""
    out: dict[str, Any] = {
        "projects_with_name": None,
        "projects_with_any_address": None,
        "address_fields_filled": None,
        "address_coverage_pct": None,
        "error": None,
    }
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        out["error"] = "missing LARK credentials"
        return out

    try:
        from bot.lark_bitable import get_tenant_access_token, list_records
        from bot.workflow_form_dispatch import _field_text
        from bot.workflow_lark_wallet_group import ADDRESS_FIELDS

        token = get_tenant_access_token(app_id, app_secret)
        records = list_records(
            token,
            str(getattr(config, "workflow_base_app_token", "")),
            str(getattr(config, "workflow_wallet_table_id", "")),
        )
        named = 0
        with_addr = 0
        addr_filled = 0
        for record in records:
            fields = record.get("fields") or {}
            has_name = bool(_field_text(fields, "Project name"))
            if has_name:
                named += 1
            has_any = False
            for fname in ADDRESS_FIELDS:
                if _field_text(fields, fname):
                    addr_filled += 1
                    has_any = True
            if has_name and has_any:
                with_addr += 1
        out["projects_with_name"] = named
        out["projects_with_any_address"] = with_addr
        out["address_fields_filled"] = addr_filled
        out["total_rows"] = len(records)
        if named:
            out["address_coverage_pct"] = round(100.0 * with_addr / named, 1)
        else:
            out["address_coverage_pct"] = 0.0
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics: wallet table query failed: %s", exc)
        out["error"] = str(exc)
    return out


def snapshot(config: Any | None = None, *, include_lark: bool = True) -> dict[str, Any]:
    """Merge live counters + derived state (+ optional Lark wallet counts)."""
    week_days = _week_dates(7)
    day_days = _dates_covering_hours(24)
    since_7d = _window_start(hours=7 * 24)
    since_24h = _window_start(hours=24)
    with _lock:
        data = _ensure_loaded()
        counters: dict[str, dict[str, int]] = {}
        today = _today()
        hourly_since = _parse_iso_ts((data.get("notes") or {}).get("hourly_since"))
        for key in COUNTER_KEYS:
            triple = _counter_triple(
                data["counters"], key, week_days, day_days=day_days
            )
            bucket = data["counters"].get(key)
            triple["today"], _ = _window_count(
                bucket, since=since_24h, day_days=day_days, hourly_since=hourly_since
            )
            triple["week"], _ = _window_count(
                bucket, since=since_7d, day_days=week_days, hourly_since=hourly_since
            )
            counters[key] = triple
        notes = dict(data.get("notes") or {})
        updated_at = data.get("updated_at") or ""

    derived: dict[str, Any] = {}
    wallet: dict[str, Any] = {}
    if config is not None:
        derived = _derived_from_state(config)
        if include_lark:
            wallet = _wallet_table_counts(config)

    # Outbound: prefer full account send counter; fall back to auto-action sum.
    c = counters
    sent = c.get("messages_sent") or {}
    auto_total = (
        int((c.get("faq_bubbles_sent") or {}).get("total") or 0)
        + int((c.get("faq_footer_sent") or {}).get("total") or 0)
        + int((c.get("welcome_messages_sent") or {}).get("total") or 0)
        + int((c.get("form_dispatch_success") or {}).get("total") or 0)
        + int((c.get("social_chitchat_replies") or {}).get("total") or 0)
    )
    auto_week = (
        int((c.get("faq_bubbles_sent") or {}).get("week") or 0)
        + int((c.get("faq_footer_sent") or {}).get("week") or 0)
        + int((c.get("welcome_messages_sent") or {}).get("week") or 0)
        + int((c.get("form_dispatch_success") or {}).get("week") or 0)
        + int((c.get("social_chitchat_replies") or {}).get("week") or 0)
    )
    auto_today = (
        int((c.get("faq_bubbles_sent") or {}).get("today") or 0)
        + int((c.get("faq_footer_sent") or {}).get("today") or 0)
        + int((c.get("welcome_messages_sent") or {}).get("today") or 0)
        + int((c.get("form_dispatch_success") or {}).get("today") or 0)
        + int((c.get("social_chitchat_replies") or {}).get("today") or 0)
    )
    outbound = {
        "total": int(sent.get("total") or 0) or auto_total,
        "week": int(sent.get("week") or 0) or auto_week,
        "today": int(sent.get("today") or 0) or auto_today,
        "auto_total": auto_total,
        "auto_week": auto_week,
        "auto_today": auto_today,
    }

    return {
        "timezone": "Asia/Shanghai",
        "today": today,
        "week_start": week_days[0] if week_days else today,
        "week_end": week_days[-1] if week_days else today,
        "window_24h_since": since_24h.isoformat(timespec="seconds"),
        "window_7d_since": since_7d.isoformat(timespec="seconds"),
        "window_until": _now_iso(),
        "updated_at": updated_at,
        "enabled": _enabled,
        "state_file": str(_state_path),
        "notes": notes,
        "counters": counters,
        "derived": derived,
        "wallet_lark": wallet,
        "outbound_messages": outbound,
        "delivery_funnels": _safe_snapshot_funnels(
            config, since_24h=since_24h, since_7d=since_7d
        ),
    }


def _fmt_triple(item: dict[str, Any] | None) -> str:
    item = item or {}
    return (
        f"{int(item.get('total') or 0)}"
        f"（过去7天 {int(item.get('week') or 0)} / 过去24小时 {int(item.get('today') or 0)}）"
    )


def format_stats_zh(snap: dict[str, Any]) -> str:
    """Readable Chinese summary for Telegram operators (full detail)."""
    c = snap.get("counters") or {}
    d = snap.get("derived") or {}
    w = snap.get("wallet_lark") or {}
    o = snap.get("outbound_messages") or {}
    today = snap.get("today") or _today()
    week_start = snap.get("week_start") or today
    week_end = snap.get("week_end") or today

    def pair(key: str) -> str:
        return _fmt_triple(c.get(key))

    logo_state = d.get("logo_fill_state") or {}
    lines = [
        f"交付自动化统计（{today} Asia/Shanghai）",
        f"过去7天窗口：{week_start} ~ {week_end}",
        f"过去24小时：{snap.get('window_24h_since') or '—'} ~ {snap.get('window_until') or '—'}",
        "",
        "【发出消息】交付号全部出站（含手动）；括号内为自动链路合计",
        f"· 全部出站：{pair('messages_sent')}",
        f"· 自动合计（FAQ气泡+页脚+欢迎+表单+社交）：{_fmt_triple({'total': o.get('auto_total', 0), 'week': o.get('auto_week', 0), 'today': o.get('auto_today', 0)})}",
        f"· FAQ 答疑会话：{pair('faq_reply_sessions')}",
        f"· FAQ 气泡条数：{pair('faq_bubbles_sent')}",
        f"· FAQ footer：{pair('faq_footer_sent')}",
        "",
        "【欢迎语】",
        f"· 欢迎序列启动：{pair('welcome_sequences_started')}",
        f"· 欢迎消息条数：{pair('welcome_messages_sent')}",
        f"· 已问候群（存量）：{d.get('welcome_greeted_count', '—')}",
        f"· 待问候 pending：{d.get('welcome_pending_count', '—')}",
        "",
        "【对接群 / 学习】",
        (
            f"· 过去7天新增合作群：{int((c.get('welcome_sequences_started') or {}).get('week') or 0)}"
            f"（过去24小时 {int((c.get('welcome_sequences_started') or {}).get('today') or 0)}；"
            f"口径=首次欢迎语）"
        ),
        f"· Absorb 成功：{pair('absorb_learn_success')}",
        f"· Agent KB 同步：{pair('agent_kb_lark_sync_success')}",
        f"· learned 文件数：{d.get('learned_md_count', '—')}",
        "",
        "【表单 / Logo / 上线】",
        f"· 表单发送成功：{pair('form_dispatch_success')}",
        f"· 表单跳过（含轮询已处理）：{pair('form_dispatch_skip')}",
        f"· 表单失败：{pair('form_dispatch_fail')}",
        f"· 表单已处理存量：{d.get('form_dispatch_processed', '—')}",
        f"· Logo 成功（埋点后）：{pair('logo_fill_success')}",
        f"· Logo 失败：{pair('logo_fill_fail')}",
        f"· Logo 无图：{pair('logo_fill_no_logo')}",
        (
            f"· Logo 存量汇总：成功 {logo_state.get('success', 0)} / "
            f"失败 {logo_state.get('fail', 0)} / "
            f"无图 {logo_state.get('no_logo', 0)} / "
            f"其他 {logo_state.get('other', 0)} "
            f"（processed={logo_state.get('processed', 0)}）"
        ),
        f"· Mark-live：{pair('mark_live_triggers')}",
        f"· /send_form：{pair('send_form_triggers')}",
        "",
        "【Webhook / 轮询】",
        f"· Webhook 收到：{pair('webhook_live_received')}",
        f"· Webhook 已处理：{pair('webhook_live_processed')}",
        f"· 轮询周期：{pair('poll_cycles_run')}",
        "",
        "【钱包表 / Digest】",
        f"· Digest 新项目：{pair('wallet_digest_new_projects')}",
        f"· Digest 已发送：{pair('wallet_digest_sent')}",
        f"· 今日新项目（状态）：{d.get('wallet_digest_new_today_from_state', '—')}",
        f"· 上次 digest：{d.get('wallet_digest_last_date') or '—'}",
    ]
    if w.get("error"):
        lines.append(f"· Lark 钱包表查询失败：{w['error']}")
    else:
        lines.append(f"· 有项目名行数：{w.get('projects_with_name', '—')}")
        lines.append(
            f"· 至少填 1 个地址的项目：{w.get('projects_with_any_address', '—')}"
            f"（覆盖率 {w.get('address_coverage_pct', '—')}%）"
        )
        lines.append(f"· 地址字段已填次数：{w.get('address_fields_filled', '—')}")
        if w.get("total_rows") is not None:
            lines.append(f"· 钱包表总行数：{w['total_rows']}")

    lines.extend(
        [
            "",
            "说明：累计计数从埋点上线后起算；存量以状态文件/飞书为准。",
            f"计数文件：{snap.get('state_file')}",
            f"更新时间：{snap.get('updated_at') or '—'}",
        ]
    )
    return "\n".join(lines)


# Progress Tracker：用中文前缀匹配飞书选项（完整文案在私有 config，不入库）
_FIELD_MAINNET_LIVE_TIME = "主网上线时间"
_FIELD_TRACK_ENTRY_TIME = "录入时间"
_FIELD_KPI_FINAL = "KPI Final"
_FIELD_KPI_WRITTEN = "written time"
_FIELD_KPI_WRITTEN_FALLBACK = "KPI 判定时间"
_KPI_COORD_PASS = frozenset({"通过", "有效 KPI"})


def _status_kind(status: str) -> str | None:
    s = (status or "").strip()
    if not s:
        return None
    if s.startswith("BOT主网上线") or s.startswith("主网上线"):
        return "live"
    if s.startswith("主网部署中"):
        return "main_deploy"
    if s.startswith("测试网部署"):
        return "test_deploy"
    return None


def _ms_to_day(value: Any) -> str | None:
    """Lark date field (ms since epoch) → Asia/Shanghai YYYY-MM-DD."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, TZ).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def _fetch_progress_records(config: Any) -> tuple[list[dict[str, Any]], str | None]:
    """One progress-table read shared by the live counts and the review funnel."""
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return [], "missing LARK credentials"
    try:
        from bot.lark_bitable import get_tenant_access_token, list_records

        token = get_tenant_access_token(app_id, app_secret)
        records = list_records(
            token,
            str(getattr(config, "workflow_base_app_token", "")),
            str(getattr(config, "workflow_progress_table_id", "")),
        )
        return [row for row in (records or []) if isinstance(row, dict)], None
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics: progress table list failed: %s", exc)
        return [], str(exc)


def _progress_table_daily_counts(
    config: Any,
    today: str | None = None,
    *,
    since: datetime | None = None,
    records: list[dict[str, Any]] | None = None,
    records_error: str | None = None,
) -> dict[str, Any]:
    """Lark Progress Tracker: live/deploy/KPI stocks + windowed new rows.

    ``since`` defaults to past 24 hours. Today's live rows need current live
    status and 「主网上线时间」 inside the window. KPI today's-new uses
    ``written time`` while coordination is already 通过 / 有效 KPI.
    """
    del today  # kept for call-site compat; window uses ``since``
    since = since or _window_start(hours=24)
    out: dict[str, Any] = {
        "mainnet_live": 0,
        "mainnet_live_names": [],
        "today_mainnet_live": 0,
        "today_mainnet_live_names": [],
        "today_mainnet_live_record_ids": [],
        "today_mainnet_live_records": [],
        "mainnet_deploying": 0,
        "mainnet_deploying_names": [],
        "testnet_deploying": 0,
        "testnet_deploying_names": [],
        "kpi_coord_pass": 0,
        "kpi_coord_pass_names": [],
        "today_kpi_coord_pass": 0,
        "today_kpi_coord_pass_names": [],
        "projects_with_logo": 0,
        "lark_track_new_projects": 0,
        "total_rows": 0,
        "window_since": since.isoformat(timespec="seconds"),
        "error": None,
    }
    if records is None:
        records, records_error = _fetch_progress_records(config)
    if records_error and not records:
        out["error"] = records_error
        return out
    records = records or []

    try:
        from bot.workflow_form_dispatch import _field_text

        status_field = str(getattr(config, "workflow_status_field", "项目状态") or "项目状态")
        name_field = str(
            getattr(config, "workflow_project_name_field", "项目名称 Project Name")
            or "项目名称 Project Name"
        )
        logo_field = str(
            getattr(config, "workflow_logo_field", "项目logo（文件）") or "项目logo（文件）"
        )
        live_status = str(
            getattr(config, "workflow_trigger_status", "") or ""
        ).strip()
        from bot.workflow_kpi_write import field_result

        out["total_rows"] = len(records)
        live_stock_ids: set[str] = set()
        live_stock_names: list[str] = []
        live_names: list[str] = []
        live_record_ids: set[str] = set()
        live_records: list[dict[str, str]] = []
        main_deploy_names: list[str] = []
        test_deploy_names: list[str] = []
        kpi_stock_ids: set[str] = set()
        kpi_stock_names: list[str] = []
        kpi_today_ids: set[str] = set()
        kpi_today_names: list[str] = []
        for record in records:
            fields = record.get("fields") or {}
            raw_name = _field_text(fields, name_field)
            name = raw_name or "(未命名)"
            rid = str(record.get("record_id") or "").strip()
            status = _field_text(fields, status_field)
            kind = _status_kind(status)
            if kind == "main_deploy":
                out["mainnet_deploying"] += 1
                main_deploy_names.append(name)
            elif kind == "test_deploy":
                out["testnet_deploying"] += 1
                test_deploy_names.append(name)
            if fields.get(logo_field):
                out["projects_with_logo"] += 1
            entry_at = _ms_to_datetime(fields.get(_FIELD_TRACK_ENTRY_TIME))
            if raw_name and _in_time_window(entry_at, since=since):
                out["lark_track_new_projects"] += 1
            is_live = (live_status and status == live_status) or kind == "live"
            if is_live:
                if rid:
                    live_stock_ids.add(rid)
                live_stock_names.append(name)
                from bot.workflow_form_dispatch import field_raw

                live_at = _judge_datetime(field_raw(fields, _FIELD_MAINNET_LIVE_TIME))
                if _in_time_window(live_at, since=since):
                    if rid:
                        live_record_ids.add(rid)
                        live_records.append({"record_id": rid, "name": name})
                    live_names.append(name)
            coord = field_result(fields, _FIELD_KPI_FINAL)
            if coord in _KPI_COORD_PASS:
                if rid:
                    kpi_stock_ids.add(rid)
                kpi_stock_names.append(name)
                judged = _judge_datetime(
                    fields.get(_FIELD_KPI_WRITTEN)
                    or fields.get(_FIELD_KPI_WRITTEN_FALLBACK)
                )
                if _in_time_window(judged, since=since):
                    if rid:
                        kpi_today_ids.add(rid)
                    kpi_today_names.append(name)
        out["mainnet_live"] = (
            len(live_stock_ids) if live_stock_ids else len(set(live_stock_names))
        )
        out["mainnet_live_names"] = sorted(set(live_stock_names), key=str.lower)
        out["today_mainnet_live_record_ids"] = sorted(live_record_ids)
        out["today_mainnet_live_records"] = sorted(
            live_records, key=lambda item: (item["name"].lower(), item["record_id"])
        )
        out["today_mainnet_live_names"] = sorted(
            set(live_names), key=str.lower
        )
        out["today_mainnet_live"] = (
            len(live_record_ids) if live_record_ids else len(set(live_names))
        )
        out["mainnet_deploying_names"] = sorted(main_deploy_names, key=str.lower)
        out["testnet_deploying_names"] = sorted(test_deploy_names, key=str.lower)
        out["kpi_coord_pass"] = (
            len(kpi_stock_ids) if kpi_stock_ids else len(set(kpi_stock_names))
        )
        out["kpi_coord_pass_names"] = sorted(set(kpi_stock_names), key=str.lower)
        out["today_kpi_coord_pass"] = (
            len(kpi_today_ids) if kpi_today_ids else len(set(kpi_today_names))
        )
        out["today_kpi_coord_pass_names"] = sorted(
            set(kpi_today_names), key=str.lower
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics: progress table daily query failed: %s", exc)
        out["error"] = str(exc)
    return out


def _wallet_daily_counts(
    config: Any,
    today: str | None = None,
    *,
    window_days: list[str] | None = None,
) -> dict[str, Any]:
    """New wallet projects in the rolling window (digest first_seen day buckets)."""
    del today
    days = set(window_days or _dates_covering_hours(24))
    out: dict[str, Any] = {
        "today_new_projects": 0,
        "today_new_address_fields": 0,
        "projects_with_any_address": 0,
        "address_fields_filled": 0,
        "window_days": sorted(days),
        "error": None,
    }
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        out["error"] = "missing LARK credentials"
        return out

    try:
        from bot.lark_bitable import get_tenant_access_token, list_records
        from bot.workflow_form_dispatch import _field_text
        from bot.workflow_lark_wallet_group import ADDRESS_FIELDS

        digest_path = ROOT / str(
            getattr(
                config,
                "workflow_lark_digest_state_file",
                "data/lark_wallet_digest_state.json",
            )
        )
        first_seen = (_safe_json(digest_path).get("first_seen") or {})
        today_ids = {
            str(rid)
            for rid, day in first_seen.items()
            if str(day) in days and rid and day not in {"baseline", ""}
        }

        token = get_tenant_access_token(app_id, app_secret)
        records = list_records(
            token,
            str(getattr(config, "workflow_base_app_token", "")),
            str(getattr(config, "workflow_wallet_table_id", "")),
        )
        with_addr = 0
        addr_filled = 0
        today_projects = 0
        today_addrs = 0
        for record in records:
            rid = str(record.get("record_id") or "")
            fields = record.get("fields") or {}
            has_name = bool(_field_text(fields, "Project name"))
            filled = sum(1 for fname in ADDRESS_FIELDS if _field_text(fields, fname))
            addr_filled += filled
            if has_name and filled:
                with_addr += 1
            if rid in today_ids:
                today_projects += 1
                today_addrs += filled
        out["today_new_projects"] = today_projects
        out["today_new_address_fields"] = today_addrs
        out["projects_with_any_address"] = with_addr
        out["address_fields_filled"] = addr_filled
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics: wallet daily query failed: %s", exc)
        out["error"] = str(exc)
    return out


def _dedupe_names(names: list[Any], *, limit: int = 40) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
        if len(out) >= max(int(limit), 1):
            break
    return out


def _classify_kpi_write(text: str) -> tuple[str, str]:
    """Return (kpi_item, pass|fail|other) from a kpi_result_written text."""
    t = str(text or "")
    if "KPI 1" in t:
        item = "KPI1"
    elif "KPI 2" in t:
        item = "KPI2"
    elif "KPI 3" in t or "官网" in t:
        item = "KPI3"
    elif "KPI 4" in t or "KPI 5" in t or "产品可用" in t or "独立性" in t:
        item = "KPI45"
    elif "KPI 6" in t or "链上" in t:
        item = "KPI6"
    elif "KPI 7" in t:
        item = "KPI7"
    elif "Twitter" in t:
        item = "KPI1"
    else:
        item = "other"
    if "不通过" in t or "fail" in t.lower():
        ok = "fail"
    elif "通过" in t or "pass" in t.lower() or "Valid" in t:
        ok = "pass"
    else:
        ok = "other"
    return item, ok


def _workflow_events_path(config: Any) -> Path:
    rel = str(
        getattr(config, "workflow_events_file", "") or "data/workflow_events.jsonl"
    ).strip()
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _message_log_dir(config: Any) -> Path:
    rel = str(
        getattr(config, "metrics_message_log_dir", "") or "data/message_logs"
    ).strip()
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / path
    return path


# Both bots append to the shared event log, so per-entity counts dedupe the
# same group or record handled by each bot.
_CHAT_SCOPED_KINDS = frozenset({"folder_chat_added", "welcome_sequence_sent"})
# Counted only when the entity's first-ever event falls inside the window.
_FIRST_EVER_KINDS = frozenset({"folder_chat_added", "welcome_sequence_sent"})


def _event_entity(kind: str, row: dict[str, Any]) -> str:
    fields = ("chat_id",) if kind in _CHAT_SCOPED_KINDS else ("record_id", "chat_id")
    for field in fields:
        value = str(row.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    name = str(row.get("project_name") or "").strip().lower()
    return f"name:{name}" if name else ""


def _workflow_window_summary(
    config: Any, *, since: datetime
) -> dict[str, Any]:
    """Aggregate workflow_events.jsonl rows inside the rolling window."""
    out: dict[str, Any] = {
        "available": False,
        "total": 0,
        "by_kind": {},
        "names_by_kind": {},
        "unique_by_kind": {},
        "new_by_kind": {},
        "new_names_by_kind": {},
        "kpi_writes": {},
        "early_final": [],
        "error": None,
    }
    path = _workflow_events_path(config)
    if not path.exists():
        return out
    by_kind: dict[str, int] = {}
    names_by_kind: dict[str, list[str]] = {}
    entities_by_kind: dict[str, dict[str, str]] = {}
    seen_before: dict[str, set[str]] = {}
    kpi_writes: dict[str, dict[str, int]] = {}
    early_final: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                dt = _parse_iso_ts(row.get("ts"))
                kind = str(row.get("kind") or "unknown")
                if not _in_time_window(dt, since=since):
                    if dt is not None and kind in _FIRST_EVER_KINDS:
                        entity = _event_entity(kind, row)
                        if entity:
                            seen_before.setdefault(kind, set()).add(entity)
                    continue
                by_kind[kind] = by_kind.get(kind, 0) + 1
                name = str(row.get("project_name") or "").strip()
                if name:
                    names_by_kind.setdefault(kind, []).append(name)
                entity = _event_entity(kind, row)
                if entity:
                    entities_by_kind.setdefault(kind, {}).setdefault(entity, name)
                if kind == "kpi_result_written":
                    item, ok = _classify_kpi_write(str(row.get("text") or ""))
                    bucket = kpi_writes.setdefault(item, {"pass": 0, "fail": 0, "other": 0})
                    bucket[ok] = int(bucket.get(ok) or 0) + 1
                if kind == "kpi_early_final":
                    text = str(row.get("text") or "").strip()
                    label = f"{name or '—'} · {text}" if text else (name or "—")
                    early_final.append(label)
        out["available"] = True
        out["total"] = sum(by_kind.values())
        out["by_kind"] = by_kind
        out["names_by_kind"] = {
            k: _dedupe_names(v) for k, v in names_by_kind.items()
        }
        out["unique_by_kind"] = {k: len(v) for k, v in entities_by_kind.items()}
        for kind in _FIRST_EVER_KINDS:
            before = seen_before.get(kind) or set()
            fresh = {
                entity: name
                for entity, name in (entities_by_kind.get(kind) or {}).items()
                if entity not in before
            }
            out["new_by_kind"][kind] = len(fresh)
            out["new_names_by_kind"][kind] = _dedupe_names(
                list(fresh.values()), limit=10_000
            )
        out["kpi_writes"] = kpi_writes
        out["early_final"] = early_final[:40]
    except OSError as exc:
        logger.warning("metrics: workflow events read failed: %s", exc)
        out["error"] = str(exc)
    return out


def _message_window_summary(
    config: Any, *, since: datetime, window_days: list[str]
) -> dict[str, Any]:
    """Aggregate message_logs outcomes inside the rolling window."""
    out: dict[str, Any] = {
        "total": 0,
        "faq_replied": 0,
        "social_replied": 0,
        "silent": 0,
        "ignored": 0,
        "outbound": 0,
        "human_review": 0,
        "silent_reasons": {},
        "error": None,
    }
    log_dir = _message_log_dir(config)
    if not log_dir.exists():
        return out
    silent_reasons: dict[str, int] = {}
    try:
        for day in window_days:
            path = log_dir / f"messages-{day}.jsonl"
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    dt = _parse_iso_ts(row.get("ts"))
                    if not _in_time_window(dt, since=since):
                        continue
                    out["total"] = int(out["total"]) + 1
                    outcome = str(row.get("outcome") or "")
                    kind = str(row.get("kind") or "")
                    if outcome == "replied" and kind == "faq":
                        out["faq_replied"] = int(out["faq_replied"]) + 1
                    elif outcome == "replied" and kind == "social":
                        out["social_replied"] = int(out["social_replied"]) + 1
                    elif outcome == "silent":
                        out["silent"] = int(out["silent"]) + 1
                        reason = str(row.get("reason") or "other").strip() or "other"
                        silent_reasons[reason] = silent_reasons.get(reason, 0) + 1
                    elif outcome == "ignored":
                        out["ignored"] = int(out["ignored"]) + 1
                    elif outcome == "sent" or kind == "outbound":
                        out["outbound"] = int(out["outbound"]) + 1
                    if kind == "human_review":
                        out["human_review"] = int(out["human_review"]) + 1
        out["silent_reasons"] = dict(
            sorted(silent_reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        )
    except OSError as exc:
        logger.warning("metrics: message log read failed: %s", exc)
        out["error"] = str(exc)
    return out


def _read_chase_projects(config: Any) -> dict[str, dict[str, Any]] | None:
    """Projects with a recorded first form send.

    ``None`` means the chase file is absent, so the caller should fall back
    to workflow events. An empty dict means tracking exists and nobody was sent.
    """
    rel = str(
        getattr(config, "workflow_form_chase_state_file", "data/form_chase_state.json")
        or "data/form_chase_state.json"
    )
    path = ROOT / rel
    inbox = Path("/opt/botchain-shared/form_chase_inbox.json")
    if not path.exists() and not inbox.exists():
        return None
    projects: dict[str, dict[str, Any]] = {}
    raw = _safe_json(path) if path.exists() else {}
    stored = raw.get("projects") if isinstance(raw, dict) else None
    if isinstance(stored, dict):
        for rid, meta in stored.items():
            if isinstance(meta, dict) and meta.get("first_sent_at"):
                projects[str(rid)] = meta
    if inbox.exists():
        incoming = _safe_json(inbox).get("projects")
        if isinstance(incoming, dict):
            for rid, meta in incoming.items():
                if str(rid) in projects or not isinstance(meta, dict):
                    continue
                if meta.get("first_sent_at"):
                    projects[str(rid)] = meta
    return projects


def _form_first_send_names(
    projects: dict[str, dict[str, Any]], *, since: datetime
) -> list[str]:
    """Project names whose form was first posted inside the report window."""
    rows: list[tuple[datetime, str]] = []
    for rid, meta in projects.items():
        try:
            ts = float(meta.get("first_sent_at"))
        except (TypeError, ValueError):
            continue
        sent_at = datetime.fromtimestamp(ts, TZ)
        if sent_at < since:
            continue
        name = str(meta.get("project_name") or "").strip() or str(rid)
        rows.append((sent_at, name))
    rows.sort(key=lambda item: (item[0], item[1].lower()))
    return _dedupe_names([name for _, name in rows], limit=10_000)


def _live_without_form(
    progress: dict[str, Any], projects: dict[str, dict[str, Any]]
) -> list[str]:
    """Live rows in the window that never got a tracked form send."""
    missing: list[str] = []
    for item in progress.get("today_mainnet_live_records") or []:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("record_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if rid and rid not in projects and name:
            missing.append(name)
    return _dedupe_names(sorted(missing, key=str.lower), limit=10_000)


_KPI1_COPY = "KPI 1 - Twitter"
_KPI6_COPY = "KPI 6 - On chain interaction"
_KPI7_COPY = "KPI 7 - Ongoing operation"
_KPI_FINAL = "KPI Final"
_STAMP_RE = re.compile(r"(First check|Recheck) (\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
# Same audit writes KPI 7 within a few minutes of the first-check cells.
# A later final (补交 or calendar) lands well after that.
_SAME_AUDIT = timedelta(minutes=20)
_SCHEDULE_CANDIDATES = (
    ROOT / "data" / "kpi_schedule_state.json",
    Path("/opt/botchain-qa-tg-bot/data/kpi_schedule_state.json"),
)
_REVIEW_EVENT_CANDIDATES = (
    Path("/opt/botchain-qa-tg-bot/data/workflow_events.jsonl"),
    Path("/opt/delivery-agent/data/workflow_events.jsonl"),
)
_BUSINESS_EPOCH = datetime(2020, 1, 1, tzinfo=TZ)
# Same start as workflow_kpi_schedule.SCHEDULE_START: auto first/final only
# for mainnet-live on/after this day.
_KPI_CALENDAR_START = date(2026, 9, 30)
_COORD_PASS = frozenset({"通过", "有效 KPI"})
_COORD_FAIL = frozenset({"不通过", "KPI未通过"})
_COORD_HELD = "暂扣整改"


def _empty_delivery_funnel(error: str | None = None) -> dict[str, Any]:
    return {
        "form_sent": [],
        "form_received": [],
        "first_pass": [],
        "first_held": [],
        "final_pass": [],
        "final_fail": [],
        "error": error,
    }


def _form_received_names(
    projects: dict[str, dict[str, Any]], *, since: datetime
) -> list[str]:
    """Projects whose live-info form was filled inside the window."""
    rows: list[tuple[datetime, str]] = []
    for rid, meta in projects.items():
        if not isinstance(meta, dict) or meta.get("cancelled") or not meta.get("done"):
            continue
        try:
            ts = float(meta.get("completed_at"))
        except (TypeError, ValueError):
            continue
        done_at = datetime.fromtimestamp(ts, TZ)
        if done_at < since:
            continue
        name = str(meta.get("project_name") or "").strip() or str(rid)
        rows.append((done_at, name))
    rows.sort(key=lambda item: (item[0], item[1].lower()))
    return _dedupe_names([name for _, name in rows], limit=10_000)


def _schedule_round_days() -> tuple[dict[str, str], dict[str, str]]:
    """Record id → calendar day the first / final round was marked done."""
    best_first: dict[str, str] = {}
    best_second: dict[str, str] = {}
    for path in _SCHEDULE_CANDIDATES:
        raw = _safe_json(path)

        def _days(bucket: Any) -> dict[str, str]:
            if not isinstance(bucket, dict):
                return {}
            return {
                str(key): str(value)
                for key, value in bucket.items()
                if str(value or "").strip()
            }

        first, second = _days(raw.get("first")), _days(raw.get("second"))
        if len(first) + len(second) > len(best_first) + len(best_second):
            best_first, best_second = first, second
    return best_first, best_second


def _copy_stamps(text: str) -> list[tuple[str, datetime]]:
    found: list[tuple[str, datetime]] = []
    for kind, raw in _STAMP_RE.findall(text or ""):
        try:
            stamp = datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        except ValueError:
            continue
        found.append((kind, stamp))
    return found


def _review_outcome(row: dict[str, Any]) -> str:
    outcome = str(row.get("outcome") or "").strip()
    if outcome in {"pass", "held", "fail"}:
        return outcome
    text = str(row.get("text") or "")
    if "Valid KPI" in text or "初审通过" in text or "终审通过" in text:
        return "pass"
    if "KPI failed" in text or "终审不通过" in text:
        return "fail"
    if "暂扣" in text or "Held for rectification" in text:
        return "held"
    return ""


def _review_round(row: dict[str, Any]) -> str:
    rnd = str(row.get("review_round") or "").strip()
    if rnd in {"first", "final"}:
        return rnd
    if str(row.get("kind") or "") == "kpi_early_final" or "终审" in str(row.get("text") or ""):
        return "final"
    if "初审" in str(row.get("text") or ""):
        return "first"
    return ""


def _review_event_paths(config: Any) -> list[Path]:
    """Own log first, then the peer host so 交付号 can still count KPI reviews."""
    paths: list[Path] = []
    seen: set[str] = set()
    for path in (_workflow_events_path(config), *_REVIEW_EVENT_CANDIDATES):
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _load_review_events(config: Any) -> list[dict[str, Any]]:
    """Posted reviews and submit-triggered finals, newest file order kept."""
    rows: list[dict[str, Any]] = []
    for path in _review_event_paths(config):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    if "kpi_review_posted" not in line and "kpi_early_final" not in line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    kind = str(row.get("kind") or "")
                    if kind not in {"kpi_review_posted", "kpi_early_final"}:
                        continue
                    rows.append(row)
        except OSError as exc:
            logger.warning("metrics: review events read failed path=%s: %s", path, exc)
    return rows


def _summarize_delivery_funnel(
    *,
    since: datetime,
    form_sent_names: list[str] | None,
    chase_projects: dict[str, dict[str, Any]] | None,
    records: list[dict[str, Any]] | None,
    records_error: str | None,
    schedule_first: dict[str, str],
    schedule_second: dict[str, str],
    events: list[dict[str, Any]],
    name_field: str,
) -> dict[str, Any]:
    """Eight delivery figures for one rolling window.

    发出 is the first time the live-info form was posted. 收回 is the chase
    row marked filled. 初审 is a calendar first check whose KPI 1 / KPI 6
    cell was first written in the window. 终审 is a submit-triggered final
    or a calendar second check. A project can be both.
    """
    from bot.workflow_form_dispatch import _field_text

    out = _empty_delivery_funnel()
    if isinstance(form_sent_names, list):
        out["form_sent"] = list(form_sent_names)
    elif chase_projects is not None:
        out["form_sent"] = _form_first_send_names(chase_projects, since=since)
    if chase_projects is not None:
        out["form_received"] = _form_received_names(chase_projects, since=since)
    if records_error and not records:
        out["error"] = records_error
        return out

    seen: set[tuple[str, str]] = set()

    def _add(record_id: str, rnd: str, name: str, outcome: str) -> None:
        if rnd not in {"first", "final"} or outcome not in {"pass", "held", "fail"}:
            return
        keys = []
        if str(record_id or "").strip():
            keys.append((str(record_id).strip(), rnd))
        if str(name or "").strip():
            keys.append((str(name).strip().casefold(), rnd))
        if not keys or any(key in seen for key in keys):
            return
        seen.update(keys)
        label = (name or record_id).strip()
        if rnd == "first" and outcome == "pass":
            out["first_pass"].append(label)
        elif rnd == "first":
            out["first_held"].append(label)
        elif outcome == "pass":
            out["final_pass"].append(label)
        else:
            out["final_fail"].append(label)

    for row in events:
        stamp = _parse_iso_ts(row.get("ts"))
        if not _in_time_window(stamp, since=since):
            continue
        rnd = _review_round(row)
        outcome = _review_outcome(row)
        _add(
            str(row.get("record_id") or ""),
            rnd,
            str(row.get("project_name") or ""),
            outcome,
        )

    for record in records or []:
        rid = str(record.get("record_id") or "").strip()
        fields = record.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        name = _field_text(fields, name_field) or rid
        kpi1 = _copy_stamps(_field_text(fields, _KPI1_COPY))
        kpi6 = _copy_stamps(_field_text(fields, _KPI6_COPY))
        kpi7 = [stamp for _kind, stamp in _copy_stamps(_field_text(fields, _KPI7_COPY))]
        first_times = [
            stamp
            for kind, stamp in kpi1 + kpi6
            if kind == "First check" and stamp >= since
        ]
        if first_times and (rid, "first") not in seen:
            first_at = min(first_times)
            if schedule_first.get(rid) == first_at.strftime("%Y-%m-%d"):
                passed = any(
                    abs((stamp - first_at).total_seconds()) <= _SAME_AUDIT.total_seconds()
                    for stamp in kpi7
                )
                _add(rid, "first", name, "pass" if passed else "held")
        if (rid, "final") in seen:
            continue
        second_day = schedule_second.get(rid) or ""
        if not second_day:
            continue
        final_times = [
            stamp
            for kind, stamp in kpi1 + kpi6
            if kind == "Recheck" and stamp >= since and stamp.strftime("%Y-%m-%d") == second_day
        ]
        final_times.extend(
            stamp
            for stamp in kpi7
            if stamp >= since and stamp.strftime("%Y-%m-%d") == second_day
        )
        if not final_times:
            continue
        coord = _field_text(fields, _KPI_FINAL)
        if coord == "通过":
            _add(rid, "final", name, "pass")
        elif coord in {"不通过", "KPI未通过"}:
            _add(rid, "final", name, "fail")
    return out


def build_delivery_funnel(
    config: Any,
    *,
    since: datetime,
    records: list[dict[str, Any]] | None = None,
    records_error: str | None = None,
    chase_projects: dict[str, dict[str, Any]] | None = None,
    form_sent_names: list[str] | None = None,
) -> dict[str, Any]:
    """Live funnel for one window. Reuse a progress-table read when the caller has one."""
    if records is None and not records_error:
        records, records_error = _fetch_progress_records(config)
    if chase_projects is None:
        chase_projects = _read_chase_projects(config)
    if form_sent_names is None and chase_projects is not None:
        form_sent_names = _form_first_send_names(chase_projects, since=since)
    first_days, second_days = _schedule_round_days()
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
    )
    return _summarize_delivery_funnel(
        since=since,
        form_sent_names=form_sent_names,
        chase_projects=chase_projects,
        records=records,
        records_error=records_error,
        schedule_first=first_days,
        schedule_second=second_days,
        events=_load_review_events(config),
        name_field=name_field,
    )


def _safe_snapshot_funnels(
    config: Any | None, *, since_24h: datetime, since_7d: datetime
) -> dict[str, Any]:
    if config is None:
        return {}
    try:
        return _snapshot_delivery_funnels(
            config, since_24h=since_24h, since_7d=since_7d
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics: delivery funnel failed: %s", exc)
        failed = _empty_delivery_funnel(str(exc))
        return {"24h": failed, "7d": dict(failed)}


def _snapshot_delivery_funnels(
    config: Any, *, since_24h: datetime, since_7d: datetime
) -> dict[str, Any]:
    """24h and 7d funnels from one progress-table read."""
    records, records_error = _fetch_progress_records(config)
    chase = _read_chase_projects(config)
    first_days, second_days = _schedule_round_days()
    events = _load_review_events(config)
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
    )
    shared = {
        "chase_projects": chase,
        "records": records,
        "records_error": records_error,
        "schedule_first": first_days,
        "schedule_second": second_days,
        "events": events,
        "name_field": name_field,
        "form_sent_names": None,
    }
    return {
        "24h": _summarize_delivery_funnel(since=since_24h, **shared),
        "7d": _summarize_delivery_funnel(since=since_7d, **shared),
    }


def _event_outcomes_by_round(
    events: list[dict[str, Any]] | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """First seen first-round / final-round outcome per record id."""
    first: dict[str, str] = {}
    final: dict[str, str] = {}
    for row in events or []:
        rid = str(row.get("record_id") or "").strip()
        if not rid:
            continue
        outcome = _review_outcome(row)
        rnd = _review_round(row)
        if rnd == "first" and outcome in {"pass", "held", "fail"} and rid not in first:
            first[rid] = "held" if outcome != "pass" else "pass"
        elif rnd == "final" and outcome in {"pass", "fail"} and rid not in final:
            final[rid] = outcome
    return first, final


def _kpi_era_review_counts(
    records: list[dict[str, Any]] | None,
    events: list[dict[str, Any]] | None,
    *,
    status_field: str = "项目状态",
    today: date | None = None,
    first_days: int | None = None,
) -> dict[str, int]:
    """First/final counts for mainnet-live on/after 2026-09-30.

    初审: reached first-check day (live + current first offset).
    终审: a completed final (posted, or KPI Final closed after a Recheck).
    """
    from bot.workflow_form_dispatch import _field_text
    from bot.workflow_kpi_write import (
        field_result,
        is_mainnet_live,
        now_shanghai,
        parse_live_start,
        review_offsets,
    )

    day = today or now_shanghai().date()
    offset = first_days
    if offset is None:
        offset, _second = review_offsets()
    first_events, final_events = _event_outcomes_by_round(events)
    out = {
        "first_pass": 0,
        "first_held": 0,
        "final_pass": 0,
        "final_fail": 0,
    }
    seen_first: set[str] = set()
    seen_final: set[str] = set()
    for record in records or []:
        fields = record.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        if not is_mainnet_live(fields, status_field):
            continue
        live = parse_live_start(fields)
        if live is None or live.date() < _KPI_CALENDAR_START:
            continue
        rid = str(record.get("record_id") or "").strip()
        if not rid:
            continue
        coord = field_result(fields, _KPI_FINAL)
        kpi1 = _copy_stamps(_field_text(fields, _KPI1_COPY))
        kpi6 = _copy_stamps(_field_text(fields, _KPI6_COPY))
        kpi7 = [stamp for _kind, stamp in _copy_stamps(_field_text(fields, _KPI7_COPY))]
        first_times = [stamp for kind, stamp in kpi1 + kpi6 if kind == "First check"]
        rechecks = [stamp for kind, stamp in kpi1 + kpi6 if kind == "Recheck"]

        if rid not in seen_first and day >= live.date() + timedelta(days=offset):
            seen_first.add(rid)
            ev = first_events.get(rid)
            if ev == "pass":
                out["first_pass"] += 1
            elif ev == "held":
                out["first_held"] += 1
            elif coord in _COORD_PASS and not rechecks:
                out["first_pass"] += 1
            elif coord in _COORD_PASS or coord == _COORD_HELD or coord in _COORD_FAIL:
                out["first_held"] += 1
            elif first_times:
                first_at = min(first_times)
                passed = any(
                    abs((stamp - first_at).total_seconds()) <= _SAME_AUDIT.total_seconds()
                    for stamp in kpi7
                )
                if passed:
                    out["first_pass"] += 1
                else:
                    out["first_held"] += 1
            else:
                out["first_held"] += 1

        if rid in seen_final:
            continue
        evf = final_events.get(rid)
        if evf == "pass":
            seen_final.add(rid)
            out["final_pass"] += 1
        elif evf == "fail":
            seen_final.add(rid)
            out["final_fail"] += 1
        elif coord in _COORD_PASS and rechecks:
            seen_final.add(rid)
            out["final_pass"] += 1
        elif coord in _COORD_FAIL:
            seen_final.add(rid)
            out["final_fail"] += 1
    return out


def build_business_snapshot(config: Any) -> dict[str, Any]:
    """All-time delivery stock for the ``业务数据`` command."""
    records, records_error = _fetch_progress_records(config)
    progress = _progress_table_daily_counts(
        config,
        since=_BUSINESS_EPOCH,
        records=records,
        records_error=records_error,
    )
    funnel = build_delivery_funnel(
        config,
        since=_BUSINESS_EPOCH,
        records=records,
        records_error=records_error,
    )
    reviews = _kpi_era_review_counts(
        records,
        _load_review_events(config),
        status_field=str(
            getattr(config, "workflow_status_field", "项目状态") or "项目状态"
        ),
    )
    return {
        "mainnet_live": int(progress.get("mainnet_live") or 0),
        "kpi_pass": int(progress.get("kpi_coord_pass") or 0),
        "form_sent": len(funnel.get("form_sent") or []),
        "form_received": len(funnel.get("form_received") or []),
        "first_pass": int(reviews.get("first_pass") or 0),
        "first_held": int(reviews.get("first_held") or 0),
        "final_pass": int(reviews.get("final_pass") or 0),
        "final_fail": int(reviews.get("final_fail") or 0),
        "error": progress.get("error") or funnel.get("error"),
    }


def format_business_data_zh(snap: dict[str, Any] | None) -> str:
    """Six-line all-time business snapshot. No project name lists."""
    data = snap or {}
    if data.get("error"):
        return f"业务数据查询失败（{data['error']}）"
    first_n = int(data.get("first_pass") or 0) + int(data.get("first_held") or 0)
    final_n = int(data.get("final_pass") or 0) + int(data.get("final_fail") or 0)
    return "\n".join(
        [
            f"1. 主网上线项目累计：{int(data.get('mainnet_live') or 0)}",
            f"2. 审核通过项目累计：{int(data.get('kpi_pass') or 0)}",
            f"3. 上线项目信息表单发出：{int(data.get('form_sent') or 0)}",
            f"4. 上线项目信息表单收回：{int(data.get('form_received') or 0)}",
            (
                f"5. 初审项目：{first_n}，通过 {int(data.get('first_pass') or 0)}，"
                f"失败 {int(data.get('first_held') or 0)}"
            ),
            (
                f"6. 终审项目：{final_n}，通过 {int(data.get('final_pass') or 0)}，"
                f"失败 {int(data.get('final_fail') or 0)}"
            ),
        ]
    )


def build_daily_report(
    config: Any,
    *,
    hours: int = 24,
    calendar_day: bool = False,
) -> dict[str, Any]:
    """Assemble ops report.

    ``calendar_day=True`` (Telegram ``交付日报``): today 00:00 → now Asia/Shanghai.
    Otherwise a rolling window of ``hours`` (dashboard period panels).
    """
    week_days = _week_dates(7)
    if calendar_day:
        now = _now()
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_days = [since.strftime("%Y-%m-%d")]
        window_label = "今日"
        hours = max(int((now - since).total_seconds() // 3600) + 1, 1)
    else:
        hours = max(int(hours), 1)
        since = _window_start(hours=hours)
        window_days = _dates_covering_hours(hours)
        if hours <= 24:
            window_label = "过去24小时"
        elif hours % 24 == 0:
            window_label = f"过去{hours // 24}天"
        else:
            window_label = f"过去{hours}小时"

    with _lock:
        data = _ensure_loaded()
        counters = data["counters"]
        hourly_since = _parse_iso_ts((data.get("notes") or {}).get("hourly_since"))
        hour_exact = True

        def _c(key: str) -> dict[str, int]:
            nonlocal hour_exact
            triple = _counter_triple(counters, key, week_days, day_days=window_days)
            triple["today"], exact = _window_count(
                counters.get(key),
                since=since,
                day_days=window_days,
                hourly_since=hourly_since,
            )
            hour_exact = hour_exact and exact
            return triple

        folder = _c("folder_auto_add_success")
        logo_ok = _c("logo_fill_success")
        processed = _c("messages_processed")
        sent = _c("messages_sent")
        faq_bubbles = _c("faq_bubbles_sent")
        faq_footer = _c("faq_footer_sent")
        social = _c("social_chitchat_replies")
        welcome_msgs = _c("welcome_messages_sent")
        welcome_seq = _c("welcome_sequences_started")
        form_ok = _c("form_dispatch_success")
        form_fail = _c("form_dispatch_fail")
        human_review = _c("human_review_alerts")
        mark_live = _c("mark_live_triggers")
        wallet_digest_sent = _c("wallet_digest_sent")
        wallet_digest_new = _c("wallet_digest_new_projects")
        absorb = _c("absorb_learn_success")
        webhook_fail_proxy = _c("webhook_live_received")
        updated_at = data.get("updated_at") or ""

    auto_replies = (
        int(faq_bubbles.get("today") or 0)
        + int(faq_footer.get("today") or 0)
        + int(social.get("today") or 0)
        + int(welcome_msgs.get("today") or 0)
        + int(form_ok.get("today") or 0)
    )
    processed_window = int(processed.get("today") or 0)
    sent_window = int(sent.get("today") or 0)
    # Until messages_sent has history, fall back to auto sum so reports aren't empty.
    replied_window = sent_window if sent_window > 0 else auto_replies

    progress_records, progress_error = _fetch_progress_records(config)
    progress = _progress_table_daily_counts(
        config,
        since=since,
        records=progress_records,
        records_error=progress_error,
    )
    wallet = _wallet_daily_counts(config, window_days=window_days)
    deploy_changes: dict[str, Any] = {
        "total": 0,
        "lines": [],
        "entered_mainnet_live": [],
        "left_mainnet_live": [],
        "entered_mainnet_live_records": [],
        "entered_mainnet_deploy": [],
        "left_mainnet_deploy": [],
        "entered_testnet_deploy": [],
        "left_testnet_deploy": [],
        "baselined": False,
    }
    try:
        from bot.workflow_deploy_status_watch import summarize_window

        deploy_changes = summarize_window(config, since=since, hours=hours)
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics: deploy status summarize failed: %s", exc)
        deploy_changes["error"] = str(exc)

    workflow = _workflow_window_summary(config, since=since)
    messages = _message_window_summary(config, since=since, window_days=window_days)
    chase_projects = _read_chase_projects(config)
    form_first_send_names: list[str] | None = None
    live_without_form_names: list[str] | None = None
    if chase_projects is not None:
        form_first_send_names = _form_first_send_names(chase_projects, since=since)
        if not progress.get("error"):
            live_without_form_names = _live_without_form(progress, chase_projects)
    delivery_funnel = build_delivery_funnel(
        config,
        since=since,
        records=progress_records,
        records_error=progress_error,
        chase_projects=chase_projects,
        form_sent_names=form_first_send_names,
    )

    events_ok = bool(workflow.get("available")) and not workflow.get("error")
    new_by_kind = workflow.get("new_by_kind") or {}
    unique_by_kind = workflow.get("unique_by_kind") or {}
    wf_by_kind = workflow.get("by_kind") or {}
    if events_ok:
        folder_window = int(new_by_kind.get("folder_chat_added") or 0)
        welcome_seq_window = int(new_by_kind.get("welcome_sequence_sent") or 0)
        welcome_msg_window = int(wf_by_kind.get("welcome_sequence_sent") or 0)
        logo_window = int(unique_by_kind.get("logo_uploaded_lark") or 0)
        mark_live_window = int(unique_by_kind.get("mark_live") or 0)
    else:
        folder_window = int(folder.get("today") or 0)
        welcome_seq_window = int(welcome_seq.get("today") or 0)
        welcome_msg_window = int(welcome_msgs.get("today") or 0)
        logo_window = int(logo_ok.get("today") or 0)
        mark_live_window = int(mark_live.get("today") or 0)
    form_window = (
        len(form_first_send_names)
        if isinstance(form_first_send_names, list)
        else int(form_ok.get("today") or 0)
    )

    # Live count stays on the progress table: current mainnet-live status and
    # 主网上线时间 inside the window. A status that was flipped to live and
    # then reverted must not be added back from the status log.
    return {
        "timezone": "Asia/Shanghai",
        "today": _today(),
        "period_key": (
            "today"
            if calendar_day
            else (
                "24h"
                if hours <= 24
                else f"{hours // 24}d"
                if hours % 24 == 0
                else f"{hours}h"
            )
        ),
        "calendar_day": bool(calendar_day),
        "window_hours": hours,
        "window_label": window_label,
        "window_since": since.isoformat(timespec="seconds"),
        "window_until": _now_iso(),
        "window_days": window_days,
        "updated_at": updated_at,
        "counter_precision": "hourly" if hour_exact else "day_buckets",
        "event_counts": events_ok,
        # Keep range reports self-contained for the analytics UI.  The
        # counter series already contains this value, but the period report
        # previously omitted it and the browser treated the missing field as
        # zero for every range.
        "metrics": {
            "folder_auto_add_success": folder_window,
            "form_first_send": form_window,
            "messages_processed": processed_window,
            "lark_track_new_projects": int(
                progress.get("lark_track_new_projects") or 0
            ),
        },
        "folder_new_groups_today": folder_window,
        # 新增合作群 = 窗口内首次发欢迎语的群（号新进群），不再用 Folder 归档
        "new_coop_groups_today": welcome_seq_window,
        "logo_fill_today": logo_window,
        "logo_fill_total_metric": int(logo_ok.get("total") or 0),
        "messages_processed_24h": processed_window,
        "messages_replied_24h": replied_window,
        "messages_sent_24h": sent_window,
        "bot_messages": {
            "processed": processed_window,
            "replied": replied_window,
            "sent": sent_window,
            "auto_replied": auto_replies,
            "faq_bubbles": int(faq_bubbles.get("today") or 0),
            "faq_footer": int(faq_footer.get("today") or 0),
            "social": int(social.get("today") or 0),
            "welcome": welcome_msg_window,
            "welcome_sequences": welcome_seq_window,
            "form": form_window,
            "form_fail": int(form_fail.get("today") or 0),
            "human_review": int(human_review.get("today") or 0),
            "mark_live": mark_live_window,
            "wallet_digest_sent": int(wallet_digest_sent.get("today") or 0),
            "wallet_digest_new": int(wallet_digest_new.get("today") or 0),
            "absorb_learn": int(absorb.get("today") or 0),
            "webhook_live_received": int(webhook_fail_proxy.get("today") or 0),
        },
        "progress": progress,
        "wallet": wallet,
        "deploy_changes": deploy_changes,
        "workflow": workflow,
        "message_mix": messages,
        "form_first_send_names": form_first_send_names,
        "live_without_form_names": live_without_form_names,
        "delivery_funnel": delivery_funnel,
    }


def build_period_reports(config: Any) -> dict[str, Any]:
    """24h / 7d / 30d ops reports for the dashboard daily panel."""
    out: dict[str, Any] = {}
    for key, hours in (("24h", 24), ("7d", 7 * 24), ("30d", 30 * 24)):
        try:
            out[key] = build_daily_report(config, hours=hours)
        except Exception as exc:  # noqa: BLE001
            logger.exception("metrics: period report %s failed", key)
            out[key] = {"error": str(exc), "period_key": key, "window_label": key}
    return out


def _period_reports_path(config: Any) -> Path | None:
    raw = str(getattr(config, "metrics_period_reports_file", "") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def publish_period_reports(config: Any) -> Path | None:
    """Write 24h / 7d / 30d reports for the console to render as-is."""
    path = _period_reports_path(config)
    if path is None:
        return None
    payload = {
        "generated_at": _now_iso(),
        "source": str(ROOT),
        "reports": build_period_reports(config),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


async def period_reports_publish_loop(config: Any) -> None:
    import asyncio

    if _period_reports_path(config) is None:
        return
    interval = max(int(getattr(config, "metrics_period_reports_interval_minutes", 5) or 5), 1)
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(None, publish_period_reports, config)
        except Exception:  # noqa: BLE001
            logger.exception("metrics: publish period reports failed")
        await asyncio.sleep(interval * 60)


def _append_name_list(lines: list[str], names: list[Any]) -> None:
    """Append full project name list under a daily-report section."""
    cleaned = [str(n).strip() for n in names if str(n).strip()]
    if not cleaned:
        lines.append("   （暂无）")
        return
    for i, name in enumerate(cleaned, 1):
        lines.append(f"   {i}. {name}")


def _fmt_stock_delta_line(
    lines: list[str],
    *,
    label: str,
    stock: int,
    stock_word: str,
    today: int,
    today_word: str = "今日新增",
    today_names: list[Any] | None = None,
    name_limit: int = 12,
) -> None:
    """Cumulative/current stock with today's new names in the same line."""
    extra = ""
    names = [str(n).strip() for n in (today_names or []) if str(n).strip()]
    if int(today) > 0 and names:
        unique = _dedupe_names(names, limit=10_000)
        shown = unique[: max(int(name_limit), 1)]
        more = max(len(unique) - len(shown), 0)
        tail = f" 等另 {more} 个" if more else ""
        extra = f"：{'、'.join(shown)}{tail}"
    lines.append(
        f"· {label}：{stock_word} {int(stock)}（{today_word} {int(today)}{extra}）"
    )


def _fmt_kind_line(
    lines: list[str],
    *,
    label: str,
    count: int,
    names: list[Any] | None = None,
    empty: str = "无",
    name_limit: int = 12,
) -> None:
    if count <= 0 and not names:
        lines.append(f"· {label}：{empty}")
        return
    n = int(count)
    if names:
        unique = _dedupe_names(list(names), limit=10_000)
        shown = unique[: max(int(name_limit), 1)]
        extra = max(len(unique) - len(shown), 0)
        suffix = f" 等另 {extra} 个" if extra else ""
        joined = "、".join(shown) if shown else empty
        lines.append(f"· {label}：{n}（{joined}{suffix}）")
    else:
        lines.append(f"· {label}：{n}")


def split_telegram_text(text: str, *, limit: int = 3500) -> list[str]:
    """Split a long Telegram reply into chunks under ``limit`` characters.

    Prefers line boundaries; falls back to hard cuts when a single line is too
    long. Telegram's hard cap is 4096; keep headroom for safety.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    cap = max(int(limit), 256)
    if len(raw) <= cap:
        return [raw]
    chunks: list[str] = []
    buf = ""
    for line in raw.split("\n"):
        piece = line if not buf else f"{buf}\n{line}"
        if len(piece) <= cap:
            buf = piece
            continue
        if buf:
            chunks.append(buf)
            buf = ""
        if len(line) <= cap:
            buf = line
            continue
        start = 0
        while start < len(line):
            chunks.append(line[start : start + cap])
            start += cap
    if buf:
        chunks.append(buf)
    return chunks or [raw[:cap]]


def _append_delivery_funnel(lines: list[str], funnel: dict[str, Any] | None) -> None:
    """The eight figures operators asked to see on the Telegram daily report."""
    data = funnel or _empty_delivery_funnel()
    sent = list(data.get("form_sent") or [])
    received = list(data.get("form_received") or [])
    _fmt_kind_line(lines, label="上线项目信息表单发出", count=len(sent), names=sent)
    _fmt_kind_line(lines, label="上线项目信息表单收回", count=len(received), names=received)
    if data.get("error"):
        lines.append(f"· 初审 / 终审：查询失败（{data['error']}）")
        return
    first_pass = list(data.get("first_pass") or [])
    first_held = list(data.get("first_held") or [])
    final_pass = list(data.get("final_pass") or [])
    final_fail = list(data.get("final_fail") or [])
    lines.append(f"· 初审项目：{len(first_pass) + len(first_held)}")
    _fmt_kind_line(lines, label="初审通过", count=len(first_pass), names=first_pass)
    _fmt_kind_line(lines, label="初审失败", count=len(first_held), names=first_held)
    lines.append(f"· 终审项目：{len(final_pass) + len(final_fail)}")
    _fmt_kind_line(lines, label="终审通过", count=len(final_pass), names=final_pass)
    _fmt_kind_line(lines, label="终审失败", count=len(final_fail), names=final_fail)


def _funnel_total(funnel: dict[str, Any] | None, *keys: str) -> int:
    data = funnel or {}
    return sum(len(data.get(key) or []) for key in keys)


def format_daily_report_zh(daily: dict[str, Any]) -> str:
    """Eight-section Chinese daily digest aligned to current automation."""
    today = daily.get("today") or _today()
    since = daily.get("window_since") or ""
    until = daily.get("window_until") or ""
    window = daily.get("window_label") or "过去24小时"
    p = daily.get("progress") or {}
    w = daily.get("wallet") or {}
    dc = daily.get("deploy_changes") or {}
    bm = daily.get("bot_messages") or {}
    wf = daily.get("workflow") or {}
    mm = daily.get("message_mix") or {}
    by_kind = wf.get("by_kind") or {}
    names_by_kind = wf.get("names_by_kind") or {}

    def kcount(kind: str) -> int:
        return int(by_kind.get(kind) or 0)

    def knames(kind: str) -> list[str]:
        return list(names_by_kind.get(kind) or [])

    precision = (
        "按小时"
        if daily.get("counter_precision") == "hourly"
        else "按自然日近似（小时桶积累中）"
    )
    lines = [
        "Delivery Agent日报",
        f"统计窗口：{window}（Asia/Shanghai）",
        f"起止：{since or '—'} ~ {until or '—'}",
        f"生成日：{today}",
        f"数据更新：{daily.get('updated_at') or '—'}；计数器{precision}",
        "",
        "一、群触达",
    ]
    if daily.get("event_counts"):
        coop_names = list(
            (wf.get("new_names_by_kind") or {}).get("welcome_sequence_sent") or []
        )
    else:
        coop_names = knames("welcome_sequence_sent")
    coop_count = int(
        daily.get("new_coop_groups_today")
        if daily.get("new_coop_groups_today") is not None
        else (bm.get("welcome_sequences") or 0)
    )
    _fmt_kind_line(
        lines,
        label="新增合作群",
        count=coop_count,
        names=coop_names,
    )
    lines.append(f"· 欢迎语发出：{bm.get('welcome', 0)}")
    faq_n = int(mm.get("faq_replied") or 0) or int(bm.get("faq_bubbles") or 0)
    social_n = int(mm.get("social_replied") or 0) or int(bm.get("social") or 0)
    silent_n = int(mm.get("silent") or 0)
    ignored_n = int(mm.get("ignored") or 0)
    outbound_n = int(mm.get("outbound") or 0) or int(
        daily.get("messages_sent_24h") or bm.get("sent") or 0
    )
    lines.append(
        f"· 入站处理：{daily.get('messages_processed_24h', bm.get('processed', 0))}；"
        f"FAQ {faq_n}、社交寒暄 {social_n}、沉默 {silent_n}、忽略 {ignored_n}；"
        f"出站 {outbound_n}"
    )
    human_n = int(mm.get("human_review") or 0) or int(bm.get("human_review") or 0)
    lines.append(f"· 人工队列 / human_review：{human_n}")
    reasons = mm.get("silent_reasons") or {}
    if reasons:
        top = "、".join(f"{r} {c}" for r, c in list(reasons.items())[:5])
        lines.append(f"· 沉默主因：{top}")

    lines.extend(["", "二、部署管道"])
    entered_test = list(dc.get("entered_testnet_deploy") or [])
    entered_main = list(dc.get("entered_mainnet_deploy") or [])
    left_live = list(dc.get("left_mainnet_live") or [])
    if p.get("error"):
        lines.append(f"· 进度表业务数据：查询失败（{p['error']}）")
    else:
        _fmt_stock_delta_line(
            lines,
            label="主网上线",
            stock=int(p.get("mainnet_live") or 0),
            stock_word="累计",
            today=int(p.get("today_mainnet_live") or 0),
            today_names=list(p.get("today_mainnet_live_names") or []),
        )
        _fmt_stock_delta_line(
            lines,
            label="主网部署中",
            stock=int(p.get("mainnet_deploying") or 0),
            stock_word="当前",
            today=len(entered_main),
            today_word="今日新进",
            today_names=entered_main,
        )
        _fmt_stock_delta_line(
            lines,
            label="KPI 统筹通过",
            stock=int(p.get("kpi_coord_pass") or 0),
            stock_word="累计",
            today=int(p.get("today_kpi_coord_pass") or 0),
            today_names=list(p.get("today_kpi_coord_pass_names") or []),
        )
    if dc.get("error"):
        lines.append(f"· 部署监测读取失败：{dc['error']}")
    elif not dc.get("baselined") and int(dc.get("total") or 0) == 0:
        lines.append("· 部署监测基线中，之后开始记新增")
    else:
        lines.append(f"· 状态变迁：{int(dc.get('total') or 0)} 次")
        _fmt_kind_line(
            lines, label="新进测试网部署", count=len(entered_test), names=entered_test
        )
        _fmt_kind_line(
            lines, label="上线回退", count=len(left_live), names=left_live
        )

    lines.extend(["", "三、上线漏斗"])
    _fmt_kind_line(
        lines,
        label="Mark live",
        count=int(bm.get("mark_live") or 0),
        names=knames("mark_live"),
    )
    _fmt_kind_line(
        lines,
        label="Logo 上传",
        count=int(daily.get("logo_fill_today") or 0),
        names=knames("logo_uploaded_lark"),
    )
    _fmt_kind_line(
        lines,
        label="verification push onboard",
        count=kcount("verification_push_onboard"),
        names=knames("verification_push_onboard"),
    )
    form_names = daily.get("form_first_send_names")
    if isinstance(form_names, list):
        _fmt_kind_line(
            lines,
            label="表单新发",
            count=len(form_names),
            names=form_names,
        )
    else:
        _fmt_kind_line(
            lines,
            label="表单新发",
            count=int(bm.get("form") or kcount("form_sent") or 0),
            names=knames("form_sent"),
        )
    missing_forms = daily.get("live_without_form_names")
    if isinstance(missing_forms, list) and missing_forms:
        _fmt_kind_line(
            lines,
            label="主网上线但没有表单记录",
            count=len(missing_forms),
            names=missing_forms,
        )
    _fmt_kind_line(
        lines,
        label="表单催收",
        count=kcount("form_chase_reminder"),
        names=knames("form_chase_reminder"),
    )
    _fmt_kind_line(
        lines,
        label="表单下发失败",
        count=int(bm.get("form_fail") or kcount("form_dispatch_failed") or 0),
        names=knames("form_dispatch_failed"),
    )
    _fmt_kind_line(
        lines,
        label="live onboard 飞书推送",
        count=kcount("live_onboard_lark_push"),
        names=knames("live_onboard_lark_push"),
    )
    _fmt_kind_line(
        lines,
        label="表单回执通知",
        count=kcount("form_received_notified"),
        names=knames("form_received_notified"),
    )

    lines.extend(["", "四、物料与钱包"])
    _fmt_kind_line(
        lines,
        label="项目信息提交",
        count=kcount("project_info_submit"),
        names=knames("project_info_submit"),
    )
    _fmt_kind_line(
        lines,
        label="PR support → KPI2",
        count=kcount("pr_support_written"),
        names=knames("pr_support_written"),
    )
    if w.get("error"):
        lines.append(f"· 新收集钱包：查询失败（{w['error']}）")
    else:
        lines.append(
            f"· 新收集钱包项目：{w.get('today_new_projects', 0)} "
            f"（地址字段 {w.get('today_new_address_fields', 0)}；"
            f"digest 埋点 {bm.get('wallet_digest_new', 0)}）"
        )
    lines.append(f"· 钱包日报发出：{bm.get('wallet_digest_sent', 0)}")
    _fmt_kind_line(
        lines,
        label="wallet_collected 事件",
        count=kcount("wallet_collected"),
        names=knames("wallet_collected"),
    )
    _fmt_kind_line(
        lines,
        label="官推自动回填",
        count=kcount("wallet_twitter_filled"),
        names=knames("wallet_twitter_filled"),
    )

    lines.extend(["", "五、KPI 审计"])
    _append_delivery_funnel(lines, daily.get("delivery_funnel"))
    kpi_writes = wf.get("kpi_writes") or {}
    write_total = kcount("kpi_result_written")
    if write_total:
        parts = []
        for item in ("KPI1", "KPI2", "KPI3", "KPI45", "KPI6", "KPI7", "other"):
            bucket = kpi_writes.get(item) or {}
            p_ok = int(bucket.get("pass") or 0)
            p_fail = int(bucket.get("fail") or 0)
            if p_ok or p_fail:
                label = "KPI4/5" if item == "KPI45" else item
                parts.append(f"{label} 通过 {p_ok}/不通过 {p_fail}")
        lines.append(f"· 字段写入：{write_total}" + (f"（{'；'.join(parts)}）" if parts else ""))
    else:
        lines.append("· 字段写入：无")
    _fmt_kind_line(
        lines,
        label="补交终审",
        count=kcount("kpi_early_final"),
        names=list(wf.get("early_final") or knames("kpi_early_final")),
    )
    _fmt_kind_line(
        lines,
        label="日历考核推群",
        count=kcount("kpi_result_pushed"),
        names=knames("kpi_result_pushed"),
    )

    lines.extend(["", "六、协作告警"])
    _fmt_kind_line(
        lines,
        label="Verify 告警",
        count=kcount("verify_alert"),
        names=knames("verify_alert"),
    )
    _fmt_kind_line(
        lines,
        label="Tech support / 技支学习",
        count=kcount("tech_support_auto_learn"),
        names=knames("tech_support_auto_learn"),
    )
    _fmt_kind_line(
        lines,
        label="可信学习入库",
        count=int(bm.get("absorb_learn") or 0) + kcount("trusted_auto_learn"),
        names=knames("trusted_auto_learn"),
    )
    _fmt_kind_line(
        lines,
        label="AMA 邀请",
        count=kcount("ama_invite_sent"),
        names=knames("ama_invite_sent"),
    )

    lines.extend(["", "七、周表例行"])
    lines.append(
        f"· 品宣 PR 周表刷入：{kcount('pr_weekly_row')} 行；"
        f"前端周报刷入：{kcount('frontend_weekly_row')} 行"
    )
    blake_n = kcount("blake_weekly_row") + kcount("blake_weekly_ping")
    lines.append(
        f"· 前端周表相关事件：{blake_n or '无'}（正式 Lark ping 仅周一发送）"
    )

    lines.extend(["", "八、Agent / 稳定性"])
    lines.append("· 服务状态：以本机 systemd 为准（报表生成时进程存活）")
    _fmt_kind_line(
        lines,
        label="Live webhook 失败事件",
        count=kcount("live_webhook_failed"),
    )
    sync_ok = kcount("lark_sync_completed")
    sync_fail = kcount("lark_sync_failed")
    lines.append(f"· Lark 知识同步：成功 {sync_ok} / 失败 {sync_fail}")
    if wf.get("error") or mm.get("error"):
        err_bits = [x for x in (wf.get("error"), mm.get("error")) if x]
        lines.append(f"· 日志聚合告警：{'；'.join(err_bits)}")

    if daily.get("calendar_day"):
        window_note = (
            f"· 本报告统计「{window}」：Asia/Shanghai 当天 00:00 至生成时刻"
            "（不是滚动 24 小时，避免早晚几分钟拉数初审对不上）。"
        )
    else:
        window_note = f"· 本报告统计「{window}」滚动窗口内的新增（Asia/Shanghai）。"
    lines.extend(
        [
            "",
            "口径说明",
            window_note,
            "· 八块：群触达 / 部署管道 / 上线漏斗 / 物料与钱包 / KPI 审计 / 协作告警 / 周表例行 / 稳定性。",
            "· 主网上线以进度表「主网上线时间」为准；部署进出以状态监测事件为准。",
            "· 表单新发按催收跟踪的首次发送计，包含状态监听、代发、轮询和进群补发。",
            "· 上线项目信息表单发出与表单新发同一口径；收回按表单字段收齐计。",
            "· 初审失败是暂扣整改，不是 KPI failed。终审失败是 KPI failed。同一项目可以先初审再终审。",
            "· 新增合作群 = 窗口内该群首次发出欢迎语（号新进合作群）；按群去重。Logo / Mark live 按项目去重；两个号合并计。",
            "· 入站处理、FAQ、沉默等消息类只统计审核号本号；交付面板总览与本日报同一份数据。",
            "· form_dispatch_skip / 轮询次数等噪声不进正文。",
        ]
    )
    return "\n".join(lines)


def format_report_zh(snap: dict[str, Any]) -> str:
    """Management-facing report: outcomes first, ops noise last."""
    c = snap.get("counters") or {}
    d = snap.get("derived") or {}
    w = snap.get("wallet_lark") or {}
    o = snap.get("outbound_messages") or {}
    today = snap.get("today") or _today()
    week_start = snap.get("week_start") or today
    week_end = snap.get("week_end") or today
    logo_state = d.get("logo_fill_state") or {}

    def t(key: str) -> dict[str, int]:
        return c.get(key) or {"total": 0, "week": 0, "today": 0}

    faq = t("faq_reply_sessions")
    welcome_seq = t("welcome_sequences_started")
    form_ok = t("form_dispatch_success")
    logo_ok = t("logo_fill_success")
    absorb = t("absorb_learn_success")
    mark = t("mark_live_triggers")
    send_form = t("send_form_triggers")

    lines = [
        "Delivery Agent 数据报告",
        f"统计窗口：过去7天（Asia/Shanghai）",
        f"起止日：{week_start} ~ {week_end}",
        f"过去24小时：{snap.get('window_24h_since') or '—'} ~ {snap.get('window_until') or '—'}",
        f"生成日：{today}",
        f"数据更新：{snap.get('updated_at') or '—'}",
        "",
        "一、项目方触达",
        (
            f"1. 过去7天新增合作群：{welcome_seq['week']} "
            f"（过去24小时 {welcome_seq['today']}；"
            f"存量已问候群 {d.get('welcome_greeted_count', '—')}）"
        ),
        f"2. FAQ 自动答疑：累计 {faq['total']} 次会话，过去7天 {faq['week']}，过去24小时 {faq['today']}",
        f"3. Agent 对外发出消息：累计 {o.get('total', 0)}，过去7天 {o.get('week', 0)}，过去24小时 {o.get('today', 0)}"
        f"（自动合计 {o.get('auto_total', 0)} / {o.get('auto_week', 0)} / {o.get('auto_today', 0)}）",
        "",
        "二、上线交付（表单 / Logo）",
        f"1. 上线表单发出成功：累计 {form_ok['total']}，过去7天 {form_ok['week']}，过去24小时 {form_ok['today']}",
        f"2. 表单已处理项目（存量去重）：{d.get('form_dispatch_processed', '—')}",
        (
            f"3. Logo：埋点后成功 {logo_ok['total']}（过去7天 {logo_ok['week']}）；"
            f"存量成功 {logo_state.get('success', 0)} / 无图 {logo_state.get('no_logo', 0)} / "
            f"已处理 {logo_state.get('processed', 0)}"
        ),
        f"4. 人工口令：mark-live 过去7天 {mark['week']}；/send_form 过去7天 {send_form['week']}",
        "",
        "三、表单与考核",
    ]
    funnels = snap.get("delivery_funnels") or {}
    week_funnel = funnels.get("7d") or {}
    day_funnel = funnels.get("24h") or {}
    if week_funnel.get("error") or day_funnel.get("error"):
        lines.append(
            "· 初审 / 终审查询失败："
            + "；".join(
                str(item)
                for item in (week_funnel.get("error"), day_funnel.get("error"))
                if item
            )
        )
    lines.extend(
        [
            (
                f"1. 上线项目信息表单发出：过去7天 {_funnel_total(week_funnel, 'form_sent')}，"
                f"过去24小时 {_funnel_total(day_funnel, 'form_sent')}"
            ),
            (
                f"2. 上线项目信息表单收回：过去7天 {_funnel_total(week_funnel, 'form_received')}，"
                f"过去24小时 {_funnel_total(day_funnel, 'form_received')}"
            ),
            (
                f"3. 初审项目：过去7天 {_funnel_total(week_funnel, 'first_pass', 'first_held')}"
                f"（通过 {_funnel_total(week_funnel, 'first_pass')}，"
                f"失败 {_funnel_total(week_funnel, 'first_held')}），"
                f"过去24小时 {_funnel_total(day_funnel, 'first_pass', 'first_held')}"
                f"（通过 {_funnel_total(day_funnel, 'first_pass')}，"
                f"失败 {_funnel_total(day_funnel, 'first_held')}）"
            ),
            (
                f"4. 终审项目：过去7天 {_funnel_total(week_funnel, 'final_pass', 'final_fail')}"
                f"（通过 {_funnel_total(week_funnel, 'final_pass')}，"
                f"失败 {_funnel_total(week_funnel, 'final_fail')}），"
                f"过去24小时 {_funnel_total(day_funnel, 'final_pass', 'final_fail')}"
                f"（通过 {_funnel_total(day_funnel, 'final_pass')}，"
                f"失败 {_funnel_total(day_funnel, 'final_fail')}）"
            ),
            "",
            "四、知识沉淀",
        ]
    )
    lines.extend(
        [
            f"1. absorb 学习成功：累计 {absorb['total']}，过去7天 {absorb['week']}",
            f"2. 本地 learned 文件：{d.get('learned_md_count', '—')}",
            f"3. Agent KB 同步成功：{_fmt_triple(t('agent_kb_lark_sync_success'))}",
            "",
            "五、钱包地址收集（飞书存量）",
        ]
    )
    if w.get("error"):
        lines.append(f"· 查询失败：{w['error']}")
    else:
        lines.extend(
            [
                f"1. 钱包表项目行（有项目名）：{w.get('projects_with_name', '—')}",
                (
                    f"2. 至少填写 1 个地址的项目：{w.get('projects_with_any_address', '—')}"
                    f"（覆盖率 {w.get('address_coverage_pct', '—')}%）"
                ),
                f"3. 地址字段填充次数：{w.get('address_fields_filled', '—')}",
                f"4. 零点日报已发送：{_fmt_triple(t('wallet_digest_sent'))}",
            ]
        )

    wh_recv = t("webhook_live_received")
    lines.extend(
        [
            "",
            "六、系统侧（供内部说明）",
            f"· Live Webhook：收到 {wh_recv['total']} / 已处理 {t('webhook_live_processed')['total']}",
            f"· 轮询周期累计：{t('poll_cycles_run')['total']}（跳过次数偏高通常表示已处理项目被重复扫到，属正常）",
            "",
            "口径说明",
            "· 「累计」= 埋点上线后进程计数；「存量」= 状态文件或飞书表当前真相。",
            "· 「过去7天」= 滚动 7×24 小时覆盖到的日历日合计；「过去24小时」同理（埋点为日桶近似）。",
            "· 「过去7天新增合作群」= 窗口内首次对合作群发出欢迎语的次数（按群去重）；不再统计 Folder 归档。",
            "· FAQ 按「答疑会话」计，一次问题多条气泡仍算 1 次会话。",
            "· 发出消息 = 交付号全部出站（NewMessage outgoing）；自动合计 = FAQ/页脚/欢迎/表单/社交。",
            "· 上线项目信息表单发出按首次发到项目群计，收回按表单字段收齐计。",
            "· 初审失败是暂扣整改；终审失败是 KPI failed。同一项目可以先初审再终审。",
            "· 完整明细可发 /stats；本报告适合向上同步。",
        ]
    )
    return "\n".join(lines)


def write_report_file(snap: dict[str, Any], path: Path | None = None) -> Path:
    """Persist the management report next to the metrics state file."""
    target = path or (_state_path.parent / "delivery_agent_report.txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = format_report_zh(snap)
    target.write_text(text + "\n", encoding="utf-8")
    return target


def record_form_outcome(form_status: str) -> None:
    """Map live-trigger / dispatch form status string → success/skip/fail."""
    s = (form_status or "").strip()
    if s == "sent":
        inc("form_dispatch_success")
    elif s.startswith("send_failed"):
        inc("form_dispatch_fail")
    elif s in {"already_sent", "no_form_url", "skipped", "disabled"} or s.startswith(
        "no_group"
    ):
        inc("form_dispatch_skip")
    elif s:
        # unknown non-empty → treat as skip (idempotent / gated)
        inc("form_dispatch_skip")


def record_logo_outcome(logo_status: str) -> None:
    """Map logo fill status → success / fail / no_logo (ignore already_*)."""
    s = (logo_status or "").strip()
    if not s or s in {
        "disabled",
        "skipped",
        "already_processed",
        "already_has_logo",
        "baseline_has_logo",
    }:
        return
    if s.startswith("ok"):
        inc("logo_fill_success")
    elif s in {"no_logo", "no_url"}:
        inc("logo_fill_no_logo")
    else:
        inc("logo_fill_fail")
