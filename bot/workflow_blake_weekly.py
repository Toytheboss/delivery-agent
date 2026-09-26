"""Daily 00:00: refresh this week's mainnet-live rows; ping Blake Monday 00:00."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from bot.lark_bitable import (
    create_record,
    get_tenant_access_token,
    list_records,
    update_record,
)
from bot.lark_im import send_text_to_chat
from bot.project_logo import link_str, upload_bitable_image
from bot.workflow_form_dispatch import _field_text, _normalize_name

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=8))

_LIVE_TIME_FIELD = "主网上线时间"
_INTRO_PROGRESS_FIELD = "项目简介（1-2句话）"
_INTRO_WALLET_FIELD = "A brief introduction of your project"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_DEFAULT_TABLE_ID = "tblsPBJW1HUmkM6X"
_DEFAULT_VIEW_ID = "vewVJL9hzD"
_DEFAULT_AT_NAME = "Blake-APP-Android (布莱克)"

FIELD_PERIOD = "统计周期"
FIELD_NAME = "项目"
FIELD_SITE = "官网"
FIELD_INTRO_ZH = "简介 中"
FIELD_INTRO_EN = "简介 英"
FIELD_LOGO = "logo"


def week_monday(now: datetime | None = None) -> datetime:
    now = now or datetime.now(TZ)
    now = now.astimezone(TZ)
    monday = now.date() - timedelta(days=now.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=TZ)


def _ping_weekday(config: Any) -> int:
    return int(getattr(config, "workflow_blake_weekly_weekday", 0) or 0)


def _ping_hour(config: Any) -> int:
    return int(getattr(config, "workflow_blake_weekly_hour", 0) or 0)


def in_ping_window(config: Any, now: datetime | None = None) -> bool:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    return now.weekday() == _ping_weekday(config) and now.hour == _ping_hour(config)


def in_daily_window(config: Any, now: datetime | None = None) -> bool:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    return now.hour == _ping_hour(config)


def report_monday(now: datetime, *, ping: bool = False) -> datetime:
    """ISO Monday of the week being written. Ping slot uses yesterday so Sunday is included."""
    now = now.astimezone(TZ)
    if ping:
        now = now - timedelta(days=1)
    return week_monday(now)


def week_sunday(monday: datetime) -> datetime:
    return monday + timedelta(days=6)


def period_label(monday: datetime) -> str:
    sunday = week_sunday(monday)
    return f"{monday.strftime('%Y-%m-%d')} ~ {sunday.strftime('%Y-%m-%d')}"


def period_short(monday: datetime) -> str:
    sunday = week_sunday(monday)
    return f"{monday.month}/{monday.day}–{sunday.month}/{sunday.day}"


def looks_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _ms_to_dt(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, TZ)
    except (OverflowError, OSError, ValueError):
        return None


def _status_is_live(status: str) -> bool:
    s = (status or "").strip()
    return s.startswith("BOT主网上线") or s.startswith("主网上线")


def _state_path(config: Any) -> Path:
    rel = getattr(config, "workflow_blake_weekly_state_file", "") or (
        "data/blake_weekly_state.json"
    )
    path = Path(rel)
    return path if path.is_absolute() else ROOT / path


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


def table_url(config: Any) -> str:
    explicit = str(getattr(config, "workflow_blake_weekly_table_url", "") or "").strip()
    if explicit:
        return explicit
    app = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    table = str(
        getattr(config, "workflow_blake_weekly_table_id", "") or _DEFAULT_TABLE_ID
    ).strip()
    view = str(
        getattr(config, "workflow_blake_weekly_view_id", "") or _DEFAULT_VIEW_ID
    ).strip()
    if not app or not table:
        return ""
    url = f"https://asgnwd2jk3jn.sg.larksuite.com/base/{app}?table={table}"
    if view:
        url += f"&view={view}"
    return url


def build_blake_ping(
    *,
    count: int,
    monday: datetime,
    at_open_id: str = "",
    at_name: str = _DEFAULT_AT_NAME,
    table_url_value: str = "",
) -> str:
    name = (at_name or _DEFAULT_AT_NAME).strip()
    at = f'<at user_id="{at_open_id}">{name}</at>' if at_open_id else f"@{name}"
    lines = [
        at,
        (
            f"本周（{period_short(monday)}）Botchain 主网上线项目一共 {count} 个，"
            "官网、logo、中英简介都收齐了，麻烦帮忙上传到官网，谢谢。"
        ),
    ]
    if table_url_value:
        lines.extend(["", f"表格：{table_url_value}"])
    return "\n".join(lines)


def _naive_pair(source: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", (source or "").strip())
    if len(text) > 160:
        text = text[:157].rstrip() + "…"
    if looks_chinese(source):
        return text, ""
    return "", text


def _llm_intros(config: Any, source: str, project_name: str) -> tuple[str, str] | None:
    source = (source or "").strip()
    if not source:
        return None
    try:
        from bot.rag import resolve_llm_credentials

        creds = resolve_llm_credentials(config)
        if creds is None:
            return None
        from openai import OpenAI

        client = OpenAI(api_key=creds.api_key, base_url=creds.base_url)
        prompt = (
            "Compress this project intro into 1-2 sentences for an official website. "
            "Keep the brand name unchanged. Do not mention Ethereum or testnet. "
            f"Project name: {project_name}\n\n"
            f"Source:\n{source}\n\n"
            'Return JSON only: {"zh":"...","en":"..."}'
        )
        resp = client.chat.completions.create(
            model=creds.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
        data = json.loads(raw)
        zh = str(data.get("zh") or "").strip()
        en = str(data.get("en") or "").strip()
        if zh or en:
            return zh, en
    except Exception:
        logger.exception("blake weekly: intro translation failed for %s", project_name)
    return None


def _logo_file_tokens(fields: dict[str, Any], logo_field: str) -> list[dict[str, str]]:
    value = fields.get(logo_field)
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        token = str(item.get("file_token") or item.get("token") or "").strip()
        if token:
            out.append({"file_token": token})
    return out


def _download_media(token: str, file_token: str) -> bytes | None:
    resp = requests.get(
        f"https://open.larksuite.com/open-apis/drive/v1/medias/{file_token}/download",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )
    if resp.status_code != 200 or not resp.content:
        return None
    return resp.content


def _copy_logo(
    token: str,
    app_token: str,
    dest_table: str,
    dest_record: str,
    src_fields: dict[str, Any],
    logo_field: str,
) -> bool:
    items = _logo_file_tokens(src_fields, logo_field)
    if not items:
        return False
    try:
        update_record(
            token, app_token, dest_table, dest_record, {FIELD_LOGO: items}
        )
        return True
    except Exception:
        logger.info("blake weekly: file_token copy failed, re-uploading")
    copied = False
    for item in items:
        raw = _download_media(token, item["file_token"])
        if not raw:
            continue
        name = "logo.bin"
        try:
            file_token = upload_bitable_image(token, app_token, raw, name)
            update_record(
                token,
                app_token,
                dest_table,
                dest_record,
                {FIELD_LOGO: [{"file_token": file_token}]},
            )
            copied = True
            break
        except Exception:
            logger.exception("blake weekly: logo re-upload failed")
    return copied


def _wallet_intro_index(wallet_records: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for record in wallet_records:
        fields = record.get("fields") or {}
        name = _normalize_name(_field_text(fields, "Project name"))
        intro = _field_text(fields, _INTRO_WALLET_FIELD)
        if name and intro:
            out[name] = intro
    return out


def collect_week_projects(
    progress_records: list[dict[str, Any]],
    *,
    monday: datetime,
    status_field: str,
    name_field: str,
    live_link_field: str,
    logo_field: str,
    wallet_intros: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    end = monday + timedelta(days=7)
    wallet_intros = wallet_intros or {}
    rows: list[dict[str, Any]] = []
    for record in progress_records:
        fields = record.get("fields") or {}
        if not _status_is_live(_field_text(fields, status_field)):
            continue
        live_at = _ms_to_dt(fields.get(_LIVE_TIME_FIELD))
        if live_at is None or live_at < monday or live_at >= end:
            continue
        name = _field_text(fields, name_field)
        if not name:
            continue
        intro = _field_text(fields, _INTRO_PROGRESS_FIELD)
        if not intro:
            intro = wallet_intros.get(_normalize_name(name), "")
        rows.append(
            {
                "record_id": str(record.get("record_id") or ""),
                "name": name,
                "site": link_str(fields.get(live_link_field)),
                "intro_source": intro,
                "logo_fields": fields,
                "live_at": live_at,
            }
        )
    rows.sort(key=lambda r: (r["live_at"], r["name"].lower()))
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
    projects: list[dict[str, Any]],
    *,
    monday: datetime,
) -> list[str]:
    app = config.workflow_base_app_token
    dest_table = str(
        getattr(config, "workflow_blake_weekly_table_id", "") or _DEFAULT_TABLE_ID
    )
    period = period_label(monday)
    dest_records = list_records(token, app, dest_table)
    existing = _dest_index(dest_records, period)
    logo_field = str(getattr(config, "workflow_logo_field", "") or "项目logo（文件）")
    kept: list[str] = []
    for project in projects:
        name = project["name"]
        key = _normalize_name(name)
        dest = existing.get(key)
        dest_fields = (dest or {}).get("fields") or {}
        zh = _field_text(dest_fields, FIELD_INTRO_ZH)
        en = _field_text(dest_fields, FIELD_INTRO_EN)
        if not zh or not en:
            pair = _llm_intros(config, project["intro_source"], name) or _naive_pair(
                project["intro_source"]
            )
            if pair:
                zh = zh or pair[0]
                en = en or pair[1]
        payload: dict[str, Any] = {
            FIELD_PERIOD: period,
            FIELD_NAME: name,
        }
        site = project.get("site") or _field_text(dest_fields, FIELD_SITE)
        if site:
            payload[FIELD_SITE] = site
        if zh:
            payload[FIELD_INTRO_ZH] = zh
        if en:
            payload[FIELD_INTRO_EN] = en
        if dest:
            rid = str(dest.get("record_id") or "")
            update_record(token, app, dest_table, rid, payload)
        else:
            rid = create_record(token, app, dest_table, payload)
            existing[key] = {"record_id": rid, "fields": payload}
        if rid and not (dest_fields.get(FIELD_LOGO)):
            _copy_logo(
                token, app, dest_table, rid, project.get("logo_fields") or {}, logo_field
            )
        if rid:
            kept.append(rid)
    return kept


def run_blake_weekly_once(
    config: Any, *, now: datetime | None = None, force: bool = False
) -> dict[str, Any]:
    """Refresh this week's live projects daily; ping the group on Monday 00:00."""
    result: dict[str, Any] = {
        "sent": False,
        "updated": False,
        "skipped": False,
        "reason": "",
        "count": 0,
        "period": "",
    }
    if not bool(getattr(config, "workflow_blake_weekly_enabled", False)):
        result["skipped"] = True
        result["reason"] = "disabled"
        return result

    now = (now or datetime.now(TZ)).astimezone(TZ)
    ping_slot = in_ping_window(config, now)
    should_ping = force or ping_slot
    monday = report_monday(now, ping=ping_slot)
    period = period_label(monday)
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
        logger.warning("blake weekly: LARK_APP_ID/SECRET missing")
        return result

    token = get_tenant_access_token(app_id, app_secret)
    progress = list_records(
        token, config.workflow_base_app_token, config.workflow_progress_table_id
    )
    wallet_intros: dict[str, str] = {}
    wallet_table = str(getattr(config, "workflow_wallet_table_id", "") or "").strip()
    if wallet_table:
        try:
            wallet_intros = _wallet_intro_index(
                list_records(token, config.workflow_base_app_token, wallet_table)
            )
        except Exception:
            logger.exception("blake weekly: wallet intro lookup failed")

    projects = collect_week_projects(
        progress,
        monday=monday,
        status_field=str(getattr(config, "workflow_status_field", "") or "项目状态"),
        name_field=str(
            getattr(config, "workflow_project_name_field", "")
            or "项目名称 Project Name"
        ),
        live_link_field=str(
            getattr(config, "workflow_live_link_field", "") or "已上线链接🔗"
        ),
        logo_field=str(getattr(config, "workflow_logo_field", "") or "项目logo（文件）"),
        wallet_intros=wallet_intros,
    )
    result["count"] = len(projects)
    upsert_week_rows(token, config, projects, monday=monday)
    result["updated"] = True
    state["last_upsert_date"] = today
    state["last_period"] = period
    state["last_count"] = len(projects)

    chat_id = str(getattr(config, "workflow_blake_weekly_chat_id", "") or "").strip()
    if not should_ping:
        _save_state(state_path, state)
        result["reason"] = "daily_update"
        logger.info(
            "blake weekly table updated period=%s count=%d", period, len(projects)
        )
        return result
    if not projects:
        _save_state(state_path, state)
        result["skipped"] = True
        result["reason"] = "no_projects"
        logger.info("blake weekly: no live projects for %s", period)
        return result
    if not chat_id:
        _save_state(state_path, state)
        result["skipped"] = True
        result["reason"] = "missing_chat_id"
        logger.warning("blake weekly: table filled but chat_id missing")
        return result
    if not force and state.get("last_ping_period") == period:
        _save_state(state_path, state)
        result["skipped"] = True
        result["reason"] = "already_sent"
        return result

    text = build_blake_ping(
        count=len(projects),
        monday=monday,
        at_open_id=str(getattr(config, "workflow_blake_weekly_at_open_id", "") or ""),
        at_name=str(
            getattr(config, "workflow_blake_weekly_at_name", "") or _DEFAULT_AT_NAME
        ),
        table_url_value=table_url(config),
    )
    send_text_to_chat(token, chat_id, text)
    state["last_ping_period"] = period
    state["last_sent_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    _save_state(state_path, state)
    result["sent"] = True
    logger.info(
        "blake weekly sent period=%s count=%d chat=%s", period, len(projects), chat_id
    )
    return result


def _seconds_until_daily(hour: int) -> float:
    now = datetime.now(TZ)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return max((target - now).total_seconds(), 1.0)


async def blake_weekly_loop(config: Any) -> None:
    weekday = _ping_weekday(config)
    hour = _ping_hour(config)
    logger.info(
        "blake weekly daily hour=%02d:00 ping weekday=%d Asia/Shanghai",
        hour,
        weekday,
    )
    loop = asyncio.get_running_loop()
    while True:
        try:
            if in_daily_window(config):
                await loop.run_in_executor(None, run_blake_weekly_once, config)
                await asyncio.sleep(90)
                continue
            sleep_for = min(
                300.0,
                await loop.run_in_executor(None, _seconds_until_daily, hour),
            )
            await asyncio.sleep(sleep_for)
        except Exception:
            logger.exception("blake weekly loop failed")
            await asyncio.sleep(60)
