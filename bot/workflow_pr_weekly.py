"""Daily 00:00: refresh this week's PR rows; ping 品宣 Monday 00:00."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bot.lark_bitable import (
    create_record,
    get_tenant_access_token,
    list_records,
    update_record,
)
from bot.lark_im import send_text_to_chat
from bot.project_logo import link_str
from bot.workflow_form_dispatch import _field_text, _normalize_name

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=8))

_DEFAULT_TABLE_ID = "tbllA25Mz66e8wpv"
_DEFAULT_VIEW_ID = "vew1kZdFkc"
_DEFAULT_TABLE_URL = (
    "https://asgnwd2jk3jn.sg.larksuite.com/base/Kb6rbLenJa4FzWsi6pzlTkdjg0e"
    f"?table={_DEFAULT_TABLE_ID}&view={_DEFAULT_VIEW_ID}"
)
_DEFAULT_CHAT_ID = "oc_4613e10ffde1fde8dc14c1899b4520dd"
_DEFAULT_ASSIGNEES = [
    {"name": "Lighter", "open_id": "ou_0bb5c059439445d106e9889ad2d62f0e"},
    {"name": "Jasper", "open_id": "ou_a98d6abcae8e25344c6ea79262c69db7"},
]

FIELD_NAME = "项目方"
FIELD_SITE = "官网"
FIELD_PR = "主网上线PR链接"
FIELD_PERIOD = "统计周期"


def week_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Sunday 00:00 → Sunday 00:00. At Sunday hour 0, use the week that just ended."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    days_since_sunday = (now.weekday() + 1) % 7
    this_sunday = datetime(now.year, now.month, now.day, tzinfo=TZ) - timedelta(
        days=days_since_sunday
    )
    if now.weekday() == 6 and now.hour == 0:
        start = this_sunday - timedelta(days=7)
        end = this_sunday
    else:
        start = this_sunday
        end = this_sunday + timedelta(days=7)
    return start, end


def _ping_weekday(config: Any) -> int:
    return int(getattr(config, "pr_weekly_weekday", 0) or 0)


def _ping_hour(config: Any) -> int:
    return int(getattr(config, "pr_weekly_hour", 0) or 0)


def in_ping_window(config: Any, now: datetime | None = None) -> bool:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    return now.weekday() == _ping_weekday(config) and now.hour == _ping_hour(config)


def in_daily_window(config: Any, now: datetime | None = None) -> bool:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    return now.hour == _ping_hour(config)


def report_window(
    now: datetime, *, ping: bool = False
) -> tuple[datetime, datetime, datetime]:
    """Return (collect_start, collect_end, label_end).

    Daily runs use the in-progress Sun–Sun week. The Monday 00:00 ping uses
    yesterday's closed week and extends collect_end to *now* so Sunday
    daytime links are included, while the 统计周期 label stays Sun–Sun.
    """
    now = now.astimezone(TZ)
    if ping:
        start, label_end = week_window(now - timedelta(days=1))
        return start, now, label_end
    start, end = week_window(now)
    return start, end, end


def period_label(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"


def period_short(start: datetime, end: datetime) -> str:
    return f"{start.month}/{start.day}–{end.month}/{end.day}"


def _ms_to_dt(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, TZ)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _ms_to_dt(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def _state_path(config: Any) -> Path:
    rel = getattr(config, "pr_weekly_state_file", "") or "data/pr_weekly_state.json"
    path = Path(rel)
    return path if path.is_absolute() else ROOT / path


def _events_path(config: Any) -> Path:
    override = str(getattr(config, "pr_capture_events_file", "") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else ROOT / path
    shared = Path("/opt/botchain-shared/pr_capture_events.jsonl")
    if shared.parent.is_dir():
        return shared
    return ROOT / "data" / "pr_capture_events.jsonl"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def log_capture_event(
    config: Any,
    *,
    record_id: str,
    project: str,
    url: str,
    site: str = "",
    captured_at: datetime | None = None,
) -> None:
    """Append one pr-support write so Sunday can see the field's last write time."""
    rid = str(record_id or "").strip()
    name = str(project or "").strip()
    link = str(url or "").strip()
    if not rid or not name or not link:
        return
    when = (captured_at or datetime.now(TZ)).astimezone(TZ)
    path = _events_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": when.isoformat(timespec="seconds"),
        "record_id": rid,
        "project": name,
        "url": link,
        "site": str(site or "").strip(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_capture_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                out.append(item)
    except OSError:
        return []
    return out


def table_url(config: Any) -> str:
    explicit = str(getattr(config, "pr_weekly_table_url", "") or "").strip()
    if explicit:
        return explicit
    app = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    table = str(getattr(config, "pr_weekly_table_id", "") or _DEFAULT_TABLE_ID).strip()
    view = str(getattr(config, "pr_weekly_view_id", "") or _DEFAULT_VIEW_ID).strip()
    if app and table:
        url = f"https://asgnwd2jk3jn.sg.larksuite.com/base/{app}?table={table}"
        if view:
            url += f"&view={view}"
        return url
    return _DEFAULT_TABLE_URL


def _assignees(config: Any) -> list[dict[str, str]]:
    raw = getattr(config, "pr_weekly_assignees", None) or []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        oid = str(item.get("open_id") or "").strip()
        if name and oid:
            out.append({"name": name, "open_id": oid})
    return out or list(_DEFAULT_ASSIGNEES)


def build_pr_weekly_ping(
    *,
    start: datetime,
    end: datetime,
    count: int,
    assignees: list[dict[str, str]] | None = None,
    table_url_value: str = "",
) -> str:
    people = assignees or list(_DEFAULT_ASSIGNEES)
    ats = [
        f'<at user_id="{item["open_id"]}">{item["name"]}</at>' for item in people
    ]
    lines = [
        " ".join(ats),
        (
            f"本周（{period_short(start, end)}）Botchain 生态项目方推特转发需求已汇总，"
            "请品宣小伙伴查看，帮忙做社媒和社群支持，谢谢。"
        ),
    ]
    if table_url_value:
        lines.extend(["", f"表格：{table_url_value}"])
    del count  # kept in signature for tests / future "一共 N 个"
    return "\n".join(lines)


def _cell_url(fields: dict[str, Any], name: str) -> str:
    return link_str(fields.get(name)) or _field_text(fields, name)


def collect_week_prs(
    progress_records: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
    name_field: str,
    live_link_field: str,
    pr_field: str,
) -> list[dict[str, str]]:
    """Latest KPI 2 write in [start, end) per progress record."""
    by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        when = _parse_ts(event.get("ts"))
        if when is None or when < start or when >= end:
            continue
        rid = str(event.get("record_id") or "").strip()
        name = str(event.get("project") or "").strip()
        url = str(event.get("url") or "").strip()
        if not rid or not name or not url:
            continue
        prev = by_id.get(rid)
        if prev is None or when >= prev["captured_at"]:
            by_id[rid] = {
                "record_id": rid,
                "name": name,
                "url": url,
                "site": str(event.get("site") or "").strip(),
                "captured_at": when,
                "source": "event",
            }
    for record in progress_records:
        rid = str(record.get("record_id") or "").strip()
        fields = record.get("fields") or {}
        if not rid or not isinstance(fields, dict):
            continue
        url = _cell_url(fields, pr_field)
        name = _field_text(fields, name_field)
        if not url or not name:
            continue
        if rid in by_id:
            if not by_id[rid].get("site"):
                by_id[rid]["site"] = _cell_url(fields, live_link_field)
            continue
        when = _ms_to_dt(record.get("last_modified_time"))
        if when is None or when < start or when >= end:
            continue
        by_id[rid] = {
            "record_id": rid,
            "name": name,
            "url": url,
            "site": _cell_url(fields, live_link_field),
            "captured_at": when,
            "source": "record",
        }
    rows = [
        {
            "record_id": str(item["record_id"]),
            "name": str(item["name"]),
            "url": str(item["url"]),
            "site": str(item.get("site") or ""),
        }
        for item in by_id.values()
    ]
    rows.sort(key=lambda item: item["name"].lower())
    return rows


def _dest_index(
    dest_records: list[dict[str, Any]], period: str
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for record in dest_records:
        fields = record.get("fields") or {}
        if _field_text(fields, FIELD_PERIOD) != period:
            continue
        name = _field_text(fields, FIELD_NAME)
        if name:
            out[_normalize_name(name)] = record
    return out


def upsert_week_rows(
    token: str,
    config: Any,
    projects: list[dict[str, str]],
    *,
    period: str,
) -> list[str]:
    app = config.workflow_base_app_token
    dest_table = str(getattr(config, "pr_weekly_table_id", "") or _DEFAULT_TABLE_ID)
    dest_records = list_records(token, app, dest_table)
    existing = _dest_index(dest_records, period)
    kept: list[str] = []
    for project in projects:
        name = project["name"]
        key = _normalize_name(name)
        dest = existing.get(key)
        payload: dict[str, Any] = {
            FIELD_PERIOD: period,
            FIELD_NAME: name,
            FIELD_PR: project["url"],
        }
        site = project.get("site") or ""
        if site:
            payload[FIELD_SITE] = site
        elif dest:
            old_site = _field_text((dest.get("fields") or {}), FIELD_SITE)
            if old_site:
                payload[FIELD_SITE] = old_site
        if dest:
            rid = str(dest.get("record_id") or "")
            update_record(token, app, dest_table, rid, payload)
        else:
            rid = create_record(token, app, dest_table, payload)
            existing[key] = {"record_id": rid, "fields": payload}
        if rid:
            kept.append(rid)
    return kept


def run_pr_weekly_once(
    config: Any, *, now: datetime | None = None, force: bool = False
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "sent": False,
        "updated": False,
        "skipped": False,
        "reason": "",
        "count": 0,
        "period": "",
    }
    if not bool(getattr(config, "pr_weekly_enabled", False)):
        result["skipped"] = True
        result["reason"] = "disabled"
        return result

    now = (now or datetime.now(TZ)).astimezone(TZ)
    ping_slot = in_ping_window(config, now)
    should_ping = force or ping_slot
    start, collect_end, label_end = report_window(now, ping=ping_slot)
    period = period_label(start, label_end)
    result["period"] = period
    state_path = _state_path(config)
    state = _load_state(state_path)
    today = now.date().isoformat()
    if not force and state.get("last_upsert_date") == today:
        result["skipped"] = True
        result["reason"] = "already_updated"
        return result

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        result["skipped"] = True
        result["reason"] = "missing_lark_credentials"
        logger.warning("pr weekly: LARK_APP_ID/SECRET missing")
        return result

    token = get_tenant_access_token(app_id, app_secret)
    progress = list_records(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        automatic_fields=True,
    )
    events = load_capture_events(_events_path(config))
    projects = collect_week_prs(
        progress,
        events,
        start=start,
        end=collect_end,
        name_field=str(
            getattr(config, "workflow_project_name_field", "")
            or "项目名称 Project Name"
        ),
        live_link_field=str(
            getattr(config, "workflow_live_link_field", "") or "已上线链接🔗"
        ),
        pr_field=str(
            getattr(config, "pr_capture_link_field", "") or "KPI 2 - PR 新闻链接验证"
        ),
    )
    result["count"] = len(projects)
    upsert_week_rows(token, config, projects, period=period)
    result["updated"] = True
    state["last_upsert_date"] = today
    state["last_period"] = period
    state["last_count"] = len(projects)

    chat_id = str(
        getattr(config, "pr_weekly_chat_id", "") or _DEFAULT_CHAT_ID
    ).strip()
    if not should_ping:
        _save_state(state_path, state)
        result["reason"] = "daily_update"
        logger.info("pr weekly table updated period=%s count=%d", period, len(projects))
        return result
    if not projects:
        _save_state(state_path, state)
        result["skipped"] = True
        result["reason"] = "no_projects"
        logger.info("pr weekly: no PR links for %s", period)
        return result
    if not chat_id:
        _save_state(state_path, state)
        result["skipped"] = True
        result["reason"] = "missing_chat_id"
        logger.warning("pr weekly: table filled but chat_id missing")
        return result
    if not force and state.get("last_ping_period") == period:
        _save_state(state_path, state)
        result["skipped"] = True
        result["reason"] = "already_sent"
        return result

    text = build_pr_weekly_ping(
        start=start,
        end=label_end,
        count=len(projects),
        assignees=_assignees(config),
        table_url_value=table_url(config),
    )
    send_text_to_chat(token, chat_id, text)
    state["last_ping_period"] = period
    state["last_sent_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    _save_state(state_path, state)
    result["sent"] = True
    logger.info(
        "pr weekly sent period=%s count=%d chat=%s", period, len(projects), chat_id
    )
    return result


def _seconds_until_daily(hour: int) -> float:
    now = datetime.now(TZ)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return max((target - now).total_seconds(), 1.0)


async def pr_weekly_loop(config: Any) -> None:
    weekday = _ping_weekday(config)
    hour = _ping_hour(config)
    logger.info(
        "pr weekly daily hour=%02d:00 ping weekday=%d Asia/Shanghai",
        hour,
        weekday,
    )
    loop = asyncio.get_running_loop()
    while True:
        try:
            if in_daily_window(config):
                await loop.run_in_executor(None, run_pr_weekly_once, config)
                await asyncio.sleep(90)
                continue
            sleep_for = min(
                300.0,
                await loop.run_in_executor(None, _seconds_until_daily, hour),
            )
            await asyncio.sleep(sleep_for)
        except Exception:
            logger.exception("pr weekly loop failed")
            await asyncio.sleep(60)
