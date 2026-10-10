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
import threading
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


def _today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


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


def _in_time_window(dt: datetime | None, *, since: datetime) -> bool:
    return dt is not None and dt >= since


def _empty_counter() -> dict[str, Any]:
    return {"total": 0, "by_day": {}}


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
                    data["counters"][key] = {"total": total, "by_day": by_day}
                data["updated_at"] = str(raw.get("updated_at") or "")
                if isinstance(raw.get("notes"), dict):
                    data["notes"].update(raw["notes"])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.exception("metrics: failed to load %s; starting fresh", _state_path)
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
        day = _today()
        by_day = bucket.setdefault("by_day", {})
        by_day[day] = int(by_day.get(day) or 0) + n
        # Keep by_day bounded (~90 days)
        if len(by_day) > 100:
            for old in sorted(by_day.keys())[:-90]:
                by_day.pop(old, None)
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
        for key in COUNTER_KEYS:
            counters[key] = _counter_triple(
                data["counters"], key, week_days, day_days=day_days
            )
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
        "【对接群 / Folder / 学习】",
        (
            f"· 过去7天新建对接群：{int((c.get('folder_auto_add_success') or {}).get('week') or 0)}"
            f"（过去24小时 {int((c.get('folder_auto_add_success') or {}).get('today') or 0)}；"
            f"口径=Folder 自动归集成功）"
        ),
        f"· Folder 自动加入：{pair('folder_auto_add_success')}",
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


def _progress_table_daily_counts(
    config: Any,
    today: str | None = None,
    *,
    since: datetime | None = None,
) -> dict[str, Any]:
    """Lark Progress Tracker: windowed mainnet live + current deploy stocks + logos.

    ``since`` defaults to past 24 hours. Live rows are included only when the
    status is live and 「主网上线时间」 falls in the window.
    """
    del today  # kept for call-site compat; window uses ``since``
    since = since or _window_start(hours=24)
    out: dict[str, Any] = {
        "today_mainnet_live": 0,
        "today_mainnet_live_names": [],
        "today_mainnet_live_record_ids": [],
        "today_mainnet_live_records": [],
        "mainnet_deploying": 0,
        "mainnet_deploying_names": [],
        "testnet_deploying": 0,
        "testnet_deploying_names": [],
        "projects_with_logo": 0,
        "lark_track_new_projects": 0,
        "total_rows": 0,
        "window_since": since.isoformat(timespec="seconds"),
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
        token = get_tenant_access_token(app_id, app_secret)
        records = list_records(
            token,
            str(getattr(config, "workflow_base_app_token", "")),
            str(getattr(config, "workflow_progress_table_id", "")),
        )
        out["total_rows"] = len(records)
        live_names: list[str] = []
        live_record_ids: set[str] = set()
        live_records: list[dict[str, str]] = []
        main_deploy_names: list[str] = []
        test_deploy_names: list[str] = []
        for record in records:
            fields = record.get("fields") or {}
            raw_name = _field_text(fields, name_field)
            name = raw_name or "(未命名)"
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
            # Only the dedicated live timestamp establishes a new live project.
            # 更新日期 changes on later edits and must never inflate this metric.
            is_live = (live_status and status == live_status) or kind == "live"
            if not is_live:
                continue
            live_at = _ms_to_datetime(fields.get(_FIELD_MAINNET_LIVE_TIME))
            if _in_time_window(live_at, since=since):
                rid = str(record.get("record_id") or "").strip()
                if rid:
                    live_record_ids.add(rid)
                    live_records.append({"record_id": rid, "name": name})
                out["today_mainnet_live"] += 1
                live_names.append(name)
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


def _workflow_window_summary(
    config: Any, *, since: datetime
) -> dict[str, Any]:
    """Aggregate workflow_events.jsonl rows inside the rolling window."""
    out: dict[str, Any] = {
        "total": 0,
        "by_kind": {},
        "names_by_kind": {},
        "kpi_writes": {},
        "early_final": [],
        "error": None,
    }
    path = _workflow_events_path(config)
    if not path.exists():
        return out
    by_kind: dict[str, int] = {}
    names_by_kind: dict[str, list[str]] = {}
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
                if not _in_time_window(dt, since=since):
                    continue
                kind = str(row.get("kind") or "unknown")
                by_kind[kind] = by_kind.get(kind, 0) + 1
                name = str(row.get("project_name") or "").strip()
                if name:
                    names_by_kind.setdefault(kind, []).append(name)
                if kind == "kpi_result_written":
                    item, ok = _classify_kpi_write(str(row.get("text") or ""))
                    bucket = kpi_writes.setdefault(item, {"pass": 0, "fail": 0, "other": 0})
                    bucket[ok] = int(bucket.get(ok) or 0) + 1
                if kind == "kpi_early_final":
                    text = str(row.get("text") or "").strip()
                    label = f"{name or '—'} · {text}" if text else (name or "—")
                    early_final.append(label)
        out["total"] = sum(by_kind.values())
        out["by_kind"] = by_kind
        out["names_by_kind"] = {
            k: _dedupe_names(v) for k, v in names_by_kind.items()
        }
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


def build_daily_report(config: Any, *, hours: int = 24) -> dict[str, Any]:
    """Assemble ops report for a rolling window (default past 24 hours)."""
    hours = max(int(hours), 1)
    since = _window_start(hours=hours)
    window_days = _dates_covering_hours(hours)
    week_days = _week_dates(7)
    if hours <= 24:
        window_label = "过去24小时"
    elif hours % 24 == 0:
        window_label = f"过去{hours // 24}天"
    else:
        window_label = f"过去{hours}小时"

    with _lock:
        data = _ensure_loaded()
        counters = data["counters"]

        def _c(key: str) -> dict[str, int]:
            return _counter_triple(counters, key, week_days, day_days=window_days)

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

    progress = _progress_table_daily_counts(config, since=since)
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

    # Live count stays on the progress table: current mainnet-live status and
    # 主网上线时间 inside the window. A status that was flipped to live and
    # then reverted must not be added back from the status log.
    return {
        "timezone": "Asia/Shanghai",
        "today": _today(),
        "period_key": (
            "24h" if hours <= 24 else f"{hours // 24}d" if hours % 24 == 0 else f"{hours}h"
        ),
        "window_hours": hours,
        "window_label": window_label,
        "window_since": since.isoformat(timespec="seconds"),
        "window_until": _now_iso(),
        "window_days": window_days,
        "updated_at": updated_at,
        # Keep range reports self-contained for the analytics UI.  The
        # counter series already contains this value, but the period report
        # previously omitted it and the browser treated the missing field as
        # zero for every range.
        "metrics": {
            "folder_auto_add_success": int(folder.get("today") or 0),
            "lark_track_new_projects": int(
                progress.get("lark_track_new_projects") or 0
            ),
        },
        "folder_new_groups_today": int(folder.get("today") or 0),
        "logo_fill_today": int(logo_ok.get("today") or 0),
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
            "welcome": int(welcome_msgs.get("today") or 0),
            "welcome_sequences": int(welcome_seq.get("today") or 0),
            "form": int(form_ok.get("today") or 0),
            "form_fail": int(form_fail.get("today") or 0),
            "human_review": int(human_review.get("today") or 0),
            "mark_live": int(mark_live.get("today") or 0),
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


def _append_name_list(lines: list[str], names: list[Any]) -> None:
    """Append full project name list under a daily-report section."""
    cleaned = [str(n).strip() for n in names if str(n).strip()]
    if not cleaned:
        lines.append("   （暂无）")
        return
    for i, name in enumerate(cleaned, 1):
        lines.append(f"   {i}. {name}")


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
        extra = max(max(n, len(unique)) - len(shown), 0)
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

    lines = [
        "Delivery Agent日报",
        f"统计窗口：{window}（Asia/Shanghai）",
        f"起止：{since or '—'} ~ {until or '—'}",
        f"生成日：{today}",
        f"数据更新：{daily.get('updated_at') or '—'}",
        "",
        "一、群触达",
    ]
    folder_names = knames("folder_chat_added")
    _fmt_kind_line(
        lines,
        label="新群归档",
        count=int(daily.get("folder_new_groups_today") or len(folder_names) or 0),
        names=folder_names,
    )
    lines.append(
        f"· 问候序列：{bm.get('welcome_sequences', 0)}；欢迎语发出：{bm.get('welcome', 0)}"
    )
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
    if dc.get("error"):
        lines.append(f"· 部署监测读取失败：{dc['error']}")
    elif not dc.get("baselined") and int(dc.get("total") or 0) == 0:
        lines.append("· 部署监测基线中，之后开始记新增")
    else:
        lines.append(f"· 状态变迁：{int(dc.get('total') or 0)} 次")
        entered_test = list(dc.get("entered_testnet_deploy") or [])
        entered_main = list(dc.get("entered_mainnet_deploy") or [])
        left_live = list(dc.get("left_mainnet_live") or [])
        _fmt_kind_line(
            lines, label="新进测试网部署", count=len(entered_test), names=entered_test
        )
        _fmt_kind_line(
            lines, label="新进主网部署中", count=len(entered_main), names=entered_main
        )
        if p.get("error"):
            lines.append(f"· 进度表主网上线：查询失败（{p['error']}）")
        else:
            _fmt_kind_line(
                lines,
                label="进度表主网上线（按主网上线时间）",
                count=int(p.get("today_mainnet_live") or 0),
                names=list(p.get("today_mainnet_live_names") or []),
            )
        _fmt_kind_line(
            lines, label="上线回退", count=len(left_live), names=left_live
        )

    lines.extend(["", "三、上线漏斗"])
    _fmt_kind_line(
        lines,
        label="Mark live",
        count=int(bm.get("mark_live") or kcount("mark_live") or 0),
        names=knames("mark_live"),
    )
    _fmt_kind_line(
        lines,
        label="Logo 上传",
        count=int(daily.get("logo_fill_today") or kcount("logo_uploaded_lark") or 0),
        names=knames("logo_uploaded_lark"),
    )
    _fmt_kind_line(
        lines,
        label="verification push onboard",
        count=kcount("verification_push_onboard"),
        names=knames("verification_push_onboard"),
    )
    _fmt_kind_line(
        lines,
        label="表单新发",
        count=int(bm.get("form") or kcount("form_sent") or 0),
        names=knames("form_sent"),
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
        f"· Blake 周表相关事件：{blake_n or '无'}（正式 Lark ping 仅周一发送）"
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

    lines.extend(
        [
            "",
            "口径说明",
            f"· 本报告统计「{window}」滚动窗口内的新增（Asia/Shanghai）。",
            "· 八块：群触达 / 部署管道 / 上线漏斗 / 物料与钱包 / KPI 审计 / 协作告警 / 周表例行 / 稳定性。",
            "· 主网上线以进度表「主网上线时间」为准；部署进出以状态监测事件为准。",
            "· 工作流事件来自 workflow_events；消息结构来自 message_logs；计数器按日桶近似。",
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
    folder = t("folder_auto_add_success")

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
            f"1. 过去7天新建对接群：{folder['week']} "
            f"（过去24小时 {folder['today']}；累计归集 {folder['total']}）"
        ),
        f"2. FAQ 自动答疑：累计 {faq['total']} 次会话，过去7天 {faq['week']}，过去24小时 {faq['today']}",
        (
            f"3. 欢迎语：过去7天启动 {welcome_seq['week']} 次；"
            f"存量已问候群 {d.get('welcome_greeted_count', '—')} 个"
        ),
        f"4. Agent 对外发出消息：累计 {o.get('total', 0)}，过去7天 {o.get('week', 0)}，过去24小时 {o.get('today', 0)}"
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
        "三、知识沉淀",
        f"1. absorb 学习成功：累计 {absorb['total']}，过去7天 {absorb['week']}",
        f"2. 本地 learned 文件：{d.get('learned_md_count', '—')}",
        f"3. Agent KB 同步成功：{_fmt_triple(t('agent_kb_lark_sync_success'))}",
        "",
        "四、钱包地址收集（飞书存量）",
    ]
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
            "五、系统侧（供内部说明）",
            f"· Live Webhook：收到 {wh_recv['total']} / 已处理 {t('webhook_live_processed')['total']}",
            f"· 轮询周期累计：{t('poll_cycles_run')['total']}（跳过次数偏高通常表示已处理项目被重复扫到，属正常）",
            "",
            "口径说明",
            "· 「累计」= 埋点上线后进程计数；「存量」= 状态文件或飞书表当前真相。",
            "· 「过去7天」= 滚动 7×24 小时覆盖到的日历日合计；「过去24小时」同理（埋点为日桶近似）。",
            "· 「过去7天新建对接群」= 窗口内自动归入 Delivery Folder 成功次数。",
            "· FAQ 按「答疑会话」计，一次问题多条气泡仍算 1 次会话。",
            "· 发出消息 = 交付号全部出站（NewMessage outgoing）；自动合计 = FAQ/页脚/欢迎/表单/社交。",
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
