"""Shared KPI table write helpers: first check vs appended recheck."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bot.lark_bitable import list_records
from bot.workflow_form_chase import field_is_filled
from bot.workflow_form_dispatch import _field_text, _normalize_name

try:
    from zoneinfo import ZoneInfo

    SH = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    SH = timezone(timedelta(hours=8))

_ROOT = Path(__file__).resolve().parent.parent
_PASS = "通过"
_FAIL = "不通过"
_LIVE_TIME_FIELD = "主网上线时间"
_STATUS_FIELD = "项目状态"
_MIN_LIVE_DATE = datetime(2026, 9, 1, tzinfo=SH).date()
_ADDR_RE = re.compile(r"0x[a-fA-F0-9]{40}")
_CONTRACT_RE = re.compile(r"(?<![0-9a-fA-F])0x[a-fA-F0-9]{40}(?![0-9a-fA-F])")
_CONTRACT_FIELDS = (
    "Contract Addresss/主网合约",
    "Mainnet Contract Addresss",
    "Mainnet Contract Address",
)


def kpi_checks_on_this_host() -> bool:
    """KPI checks and result-cell writes run on Roy号 only.

    The delivery-agent install at ``/opt/delivery-agent`` never writes KPI
    cells. Local checkouts and Roy号 (``botchain-qa-tg-bot``) still can.
    """
    root = str(_ROOT).replace("\\", "/").lower().rstrip("/")
    return root != "/opt/delivery-agent" and not root.startswith(
        "/opt/delivery-agent/"
    )


def now_shanghai() -> datetime:
    return datetime.now(SH)


def merge_kpi_copy(existing: str, new_copy: str, when: datetime | None = None) -> str:
    """Append one timed round. The first write is First check; later ones are Recheck.

    Older cells that are a single untinned sentence stay as they are. The next
    check adds a Recheck block under them instead of rewriting that sentence.
    """
    fresh = (new_copy or "").strip()
    old = (existing or "").strip()
    if not fresh:
        return old
    stamp = (when or now_shanghai()).astimezone(SH).strftime("%Y-%m-%d %H:%M")
    title = "First check" if not old else "Recheck"
    block = f"{title} {stamp}\n{fresh}"
    if not old:
        return block
    return f"{old}\n{block}"


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


def is_mainnet_live(
    fields: dict[str, Any], status_field: str = _STATUS_FIELD
) -> bool:
    s = (
        field_result(fields, status_field)
        or _field_text(fields, status_field)
        or ""
    ).strip()
    if s.startswith("BOT主网上线") or s.startswith("主网上线"):
        return True
    return "mainnet live" in s.lower()


def diag_not_eligible_reason(
    fields: dict[str, Any], status_field: str = _STATUS_FIELD
) -> str | None:
    if not is_mainnet_live(fields, status_field):
        return "This project is not marked mainnet-live yet."
    live = parse_live_start(fields)
    if live is None or live.date() < _MIN_LIVE_DATE:
        return (
            "This command only runs for projects that went live on mainnet "
            "on or after 2026-09-01."
        )
    return None


def extract_contract(value: Any) -> str:
    match = _ADDR_RE.search(str(value or ""))
    return match.group(0).lower() if match else ""


def extract_contracts(value: Any) -> list[str]:
    """Every distinct 40-hex address, in order. A 64-hex hash is not included."""
    out: list[str] = []
    seen: set[str] = set()
    for match in _CONTRACT_RE.finditer(str(value or "")):
        addr = match.group(0).lower()
        if addr in seen:
            continue
        seen.add(addr)
        out.append(addr)
    return out


def _display_name_key(text: str) -> str:
    """Case-insensitive key that still treats spaces as part of the name."""
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


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
    exact_key = _display_name_key(project_name)
    norm_key = _normalize_name(project_name)
    exact_hits: list[tuple[str, dict[str, Any]]] = []
    norm_hits: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        if not rid:
            continue
        wallet_name = _field_text(fields, name_field)
        if exact_key and _display_name_key(wallet_name) == exact_key:
            exact_hits.append((rid, fields))
        if norm_key and _normalize_name(wallet_name) == norm_key:
            norm_hits.append((rid, fields))
    if len(exact_hits) == 1:
        return exact_hits[0]
    if len(norm_hits) == 1:
        return norm_hits[0]
    return None


def wallet_contracts(fields: dict[str, Any]) -> list[str]:
    """Addresses in the mainnet-contract cell only. Other wallet columns are ignored."""
    out: list[str] = []
    seen: set[str] = set()
    for name in _CONTRACT_FIELDS:
        if not field_is_filled(fields, name):
            continue
        for addr in extract_contracts(_field_text(fields, name) or fields.get(name)):
            if addr in seen:
                continue
            seen.add(addr)
            out.append(addr)
    return out


def wallet_contract(fields: dict[str, Any]) -> str:
    found = wallet_contracts(fields)
    return found[0] if found else ""
