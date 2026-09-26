"""Shared KPI table write helpers: first check vs appended recheck."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from bot.lark_bitable import list_records
from bot.workflow_form_chase import field_is_filled
from bot.workflow_form_dispatch import _field_text, _normalize_name

try:
    from zoneinfo import ZoneInfo

    SH = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    SH = timezone(timedelta(hours=8))

_PASS = "通过"
_FAIL = "不通过"
_LIVE_TIME_FIELD = "主网上线时间"
_ADDR_RE = re.compile(r"0x[a-fA-F0-9]{40}")


def now_shanghai() -> datetime:
    return datetime.now(SH)


def merge_kpi_copy(existing: str, new_copy: str, when: datetime | None = None) -> str:
    old = (existing or "").strip()
    fresh = (new_copy or "").strip()
    if not old:
        return fresh
    stamp = (when or now_shanghai()).astimezone(SH).strftime("%Y-%m-%d %H:%M")
    return f"{old}\n复审 {stamp}：{fresh}"


def merge_kpi_result(existing: str, *, passed: bool) -> str:
    """Recheck pass upgrades to 通过. Recheck fail does not downgrade 通过."""
    old = (existing or "").strip()
    if passed:
        return _PASS
    if old == _PASS:
        return _PASS
    return _FAIL


def select_text(value: Any) -> str:
    if isinstance(value, list) and value:
        return select_text(value[0])
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "").strip()
    return str(value or "").strip()


def field_result(fields: dict[str, Any], name: str) -> str:
    return select_text(fields.get(name)) or _field_text(fields, name)


def parse_live_start(
    fields: dict[str, Any], field: str = _LIVE_TIME_FIELD
) -> datetime | None:
    raw = _field_text(fields, field) or select_text(fields.get(field))
    if not raw:
        return None
    text = str(raw).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            ms = float(text)
            if ms > 1_000_000_000_000:
                ms /= 1000.0
            dt = datetime.fromtimestamp(ms, SH)
        except (OverflowError, OSError, TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SH)
    local = dt.astimezone(SH)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def extract_contract(value: Any) -> str:
    match = _ADDR_RE.search(str(value or ""))
    return match.group(0).lower() if match else ""


def find_wallet_row(
    token: str,
    config: Any,
    project_name: str,
) -> tuple[str, dict[str, Any]] | None:
    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    wallet_table = str(getattr(config, "workflow_wallet_table_id", "") or "").strip()
    name_field = str(
        getattr(config, "workflow_wallet_name_field", "") or "Project name"
    ).strip()
    if not app_token or not wallet_table:
        return None
    rows = list_records(token, app_token, wallet_table)
    key = _normalize_name(project_name)
    hits: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        if not rid:
            continue
        if _normalize_name(_field_text(fields, name_field)) != key:
            continue
        hits.append((rid, fields))
    if len(hits) == 1:
        return hits[0]
    return None


def wallet_contract(fields: dict[str, Any]) -> str:
    for name in (
        "Contract Addresss/主网合约",
        "Mainnet Contract Addresss",
        "Mainnet Contract Address",
    ):
        if field_is_filled(fields, name):
            found = extract_contract(_field_text(fields, name) or fields.get(name))
            if found:
                return found
    for value in (fields or {}).values():
        found = extract_contract(value)
        if found:
            return found
    return ""
