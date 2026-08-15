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
_FIELD_UPDATE_DATE = "更新日期"


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

    ``since`` defaults to past 24 hours. Live rows are included when status is live
    and 「主网上线时间」or「更新日期」falls in the window (timestamp-based).
    """
    del today  # kept for call-site compat; window uses ``since``
    since = since or _window_start(hours=24)
    out: dict[str, Any] = {
        "today_mainnet_live": 0,
        "today_mainnet_live_names": [],
        "mainnet_deploying": 0,
        "mainnet_deploying_names": [],
        "testnet_deploying": 0,
        "testnet_deploying_names": [],
        "projects_with_logo": 0,
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
        logo_field = str(getattr(config, "workflow_logo_field", "项目logo") or "项目logo")
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
        main_deploy_names: list[str] = []
        test_deploy_names: list[str] = []
        for record in records:
            fields = record.get("fields") or {}
            name = _field_text(fields, name_field) or "(未命名)"
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
            # Must be actually live — 主网上线时间 alone is often a planned date.
            is_live = (live_status and status == live_status) or kind == "live"
            if not is_live:
                continue
            live_at = _ms_to_datetime(fields.get(_FIELD_MAINNET_LIVE_TIME))
            update_at = _ms_to_datetime(fields.get(_FIELD_UPDATE_DATE))
            if _in_time_window(live_at, since=since) or _in_time_window(
                update_at, since=since
            ):
                out["today_mainnet_live"] += 1
                live_names.append(name)
        out["today_mainnet_live_names"] = sorted(live_names, key=str.lower)
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
        folder = _counter_triple(
            data["counters"], "folder_auto_add_success", week_days, day_days=window_days
        )
        logo_ok = _counter_triple(
            data["counters"], "logo_fill_success", week_days, day_days=window_days
        )
        processed = _counter_triple(
            data["counters"], "messages_processed", week_days, day_days=window_days
        )
        sent = _counter_triple(
            data["counters"], "messages_sent", week_days, day_days=window_days
        )
        faq_bubbles = _counter_triple(
            data["counters"], "faq_bubbles_sent", week_days, day_days=window_days
        )
        faq_footer = _counter_triple(
            data["counters"], "faq_footer_sent", week_days, day_days=window_days
        )
        social = _counter_triple(
            data["counters"], "social_chitchat_replies", week_days, day_days=window_days
        )
        welcome_msgs = _counter_triple(
            data["counters"], "welcome_messages_sent", week_days, day_days=window_days
        )
        form_ok = _counter_triple(
            data["counters"], "form_dispatch_success", week_days, day_days=window_days
        )
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

    # Merge status-watch "entered live in window" into the live list (deduped).
    live_names = list(progress.get("today_mainnet_live_names") or [])
    for name in deploy_changes.get("entered_mainnet_live") or []:
        if name and name not in live_names:
            live_names.append(name)
    live_names = sorted(live_names, key=str.lower)
    progress["today_mainnet_live_names"] = live_names
    progress["today_mainnet_live"] = len(live_names)

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
            "form": int(form_ok.get("today") or 0),
        },
        "progress": progress,
        "wallet": wallet,
        "deploy_changes": deploy_changes,
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


def format_daily_report_zh(daily: dict[str, Any]) -> str:
    """Short Chinese daily digest: past-24h new items only (no full stock lists)."""
    today = daily.get("today") or _today()
    since = daily.get("window_since") or ""
    until = daily.get("window_until") or ""
    p = daily.get("progress") or {}
    w = daily.get("wallet") or {}
    dc = daily.get("deploy_changes") or {}

    lines = [
        "Delivery Agent日报",
        f"统计窗口：过去24小时（Asia/Shanghai）",
        f"起止：{since or '—'} ~ {until or '—'}",
        f"生成日：{today}",
        f"数据更新：{daily.get('updated_at') or '—'}",
        "",
        "一、过去24小时上线与部署",
    ]
    if p.get("error"):
        lines.append(f"· 进度表查询失败：{p['error']}")
    else:
        lines.append(f"1. 过去24小时主网上线：{p.get('today_mainnet_live', 0)} 个")
        _append_name_list(lines, list(p.get("today_mainnet_live_names") or []))

    if dc.get("error"):
        lines.append(f"2. 过去24小时新进测试网部署：读取失败（{dc['error']}）")
        lines.append("3. 过去24小时新进主网部署中：读取失败")
    elif not dc.get("baselined") and int(dc.get("total") or 0) == 0:
        lines.append("2. 过去24小时新进测试网部署：—（监测基线中，之后开始记新增）")
        lines.append("3. 过去24小时新进主网部署中：—（监测基线中，之后开始记新增）")
    else:
        entered_test = list(dc.get("entered_testnet_deploy") or [])
        entered_main = list(dc.get("entered_mainnet_deploy") or [])
        lines.append(f"2. 过去24小时新进测试网部署：{len(entered_test)} 个")
        _append_name_list(lines, entered_test)
        lines.append(f"3. 过去24小时新进主网部署中：{len(entered_main)} 个")
        _append_name_list(lines, entered_main)

    lines.extend(
        [
            "",
            "二、过去24小时对接与物料",
            (
                f"1. 过去24小时新进项目方群：{daily.get('folder_new_groups_today', 0)} 个"
                "（Folder 自动归集成功）"
            ),
        ]
    )
    if w.get("error"):
        lines.append(f"2. 过去24小时新收集钱包：查询失败：{w['error']}")
    else:
        lines.append(
            f"2. 过去24小时新收集钱包的项目方：{w.get('today_new_projects', 0)} 个"
            f"（新增地址字段 {w.get('today_new_address_fields', 0)} 个）"
        )
    lines.append(f"3. 过去24小时收集 Logo：{daily.get('logo_fill_today', 0)} 个")

    bm = daily.get("bot_messages") or {}
    window = daily.get("window_label") or "过去24小时"
    lines.extend(
        [
            "",
            f"三、{window} Bot 消息",
            (
                f"1. 发出消息：{daily.get('messages_replied_24h', bm.get('replied', 0))} 条"
                "（交付号全部出站，含手动发送）"
            ),
            f"2. 处理入站：{daily.get('messages_processed_24h', bm.get('processed', 0))} 条",
            (
                "   （其中自动发出：FAQ 气泡 "
                f"{bm.get('faq_bubbles', 0)}、页脚 {bm.get('faq_footer', 0)}、"
                f"社交寒暄 {bm.get('social', 0)}、欢迎 {bm.get('welcome', 0)}、"
                f"表单 {bm.get('form', 0)}；自动合计 {bm.get('auto_replied', 0)}）"
            ),
        ]
    )
    lines.extend(
        [
            "",
            "口径说明",
            f"· 本报告统计「{window}」滚动窗口内的新增，不含全量存量名单。",
            "· 主网上线 = 状态已是「主网上线」，且「主网上线时间」或「更新日期」落在窗口内（或监测到该窗口内新进该状态）。",
            "· 新进测试网/主网部署 = 监测到状态在窗口内进入对应项。",
            "· 新进群 / Logo = 埋点按日桶汇总后，取覆盖窗口的日历日合计（近似）。",
            "· 新收集钱包 = digest first_seen 落在覆盖窗口的日历日。",
            "· 发出消息 = 交付号账号全部出站消息（含 FAQ/欢迎/表单/手动打字等）。",
            "· 处理入站 = 进入 FAQ/社交处理链路的入站消息数（含最终沉默未回）。",
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
            "· 发出消息估算 = FAQ 气泡 + FAQ 页脚 + 欢迎条数 + 表单成功次数。",
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
