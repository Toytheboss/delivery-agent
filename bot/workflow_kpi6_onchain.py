"""KPI 6 on-chain check: unique wallets and successful core txs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import requests

from bot.lark_bitable import update_record
from bot.workflow_form_dispatch import _field_text
from bot.workflow_kpi_write import (
    SH,
    extract_contract,
    field_result,
    find_wallet_row,
    merge_kpi_copy,
    merge_kpi_result,
    now_shanghai,
    parse_live_start,
    wallet_contract,
)

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

_DEFAULT_COPY_FIELD = "KPI 6 - 链上交互验证"
_DEFAULT_RESULT_FIELD = "交互验证结果"
_PASS = "通过"
_FAIL = "不通过"
_SCAN_API = "https://scan.botchain.ai/api"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def is_create_tx(tx: dict[str, Any]) -> bool:
    if str(tx.get("contractAddress") or "").strip():
        return True
    to_addr = str(tx.get("to") or "").strip()
    return not to_addr


def is_successful(tx: dict[str, Any]) -> bool:
    err = str(tx.get("isError") or "0").strip()
    return err in {"", "0"}


def fetch_txlist(address: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while page <= 20:
        resp = requests.get(
            _SCAN_API,
            params={
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "page": page,
                "offset": 1000,
                "sort": "asc",
            },
            headers={"User-Agent": _UA},
            timeout=45,
        )
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        items.extend(row for row in rows if isinstance(row, dict))
        if len(rows) < 1000:
            break
        page += 1
    return items


def classify_core_txs(
    txs: list[dict[str, Any]],
    *,
    contract: str,
    window_start: datetime | None,
    window_end: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ca = (contract or "").lower()
    end = window_end or now_shanghai()
    core: list[dict[str, Any]] = []
    skipped = {"create": 0, "failed": 0, "out_window": 0, "not_to": 0}
    for tx in txs:
        to_addr = str(tx.get("to") or "").strip().lower()
        if is_create_tx(tx):
            skipped["create"] += 1
            continue
        if to_addr != ca:
            skipped["not_to"] += 1
            continue
        if not is_successful(tx):
            skipped["failed"] += 1
            continue
        try:
            ts = datetime.fromtimestamp(int(tx.get("timeStamp") or 0), SH)
        except (OSError, OverflowError, TypeError, ValueError):
            skipped["out_window"] += 1
            continue
        if window_start is not None and ts < window_start:
            skipped["out_window"] += 1
            continue
        if ts > end:
            skipped["out_window"] += 1
            continue
        core.append(tx)
    return core, skipped


def unique_wallets(txs: list[dict[str, Any]], contract: str) -> list[str]:
    ca = (contract or "").lower()
    counts: dict[str, int] = {}
    for tx in txs:
        sender = str(tx.get("from") or "").strip().lower()
        if not sender or sender == ca:
            continue
        counts[sender] = counts.get(sender, 0) + 1
    return sorted(counts, key=lambda addr: (-counts[addr], addr))


def build_kpi6_copy(
    *,
    passed: bool,
    reason: str,
    wallets: list[str],
    tx_count: int,
) -> str:
    if reason == "no_contract":
        return "用户和交互验证，没有检测到合约，用户和交互验证不通过"
    n = len(wallets)
    shown = wallets[:5]
    listed = "、".join(shown) if shown else "无"
    suffix = "用户和交互验证通过" if passed else "用户和交互验证不通过"
    extra = "（此处最多只展示5个独立钱包）" if shown else ""
    return (
        f"用户和交互验证，上线日至核查日独立钱包{n}个、成功核心交易{tx_count}笔"
        f"（门槛≥3钱包且交互≥5笔），独立钱包：{listed}{extra}，{suffix}"
    )


def evaluate_kpi6(
    *,
    contract: str,
    txs: list[dict[str, Any]] | None,
    window_start: datetime | None,
) -> dict[str, Any]:
    if not contract:
        return {
            "passed": False,
            "result": _FAIL,
            "reason": "no_contract",
            "wallets": [],
            "tx_count": 0,
            "copy": build_kpi6_copy(
                passed=False, reason="no_contract", wallets=[], tx_count=0
            ),
        }
    core, _skipped = classify_core_txs(
        txs or [], contract=contract, window_start=window_start
    )
    wallets = unique_wallets(core, contract)
    tx_count = len(core)
    passed = len(wallets) >= 3 and tx_count >= 5
    return {
        "passed": passed,
        "result": _PASS if passed else _FAIL,
        "reason": "pass" if passed else "below_threshold",
        "wallets": wallets,
        "tx_count": tx_count,
        "copy": build_kpi6_copy(
            passed=passed, reason="ok", wallets=wallets, tx_count=tx_count
        ),
    }


def audit_kpi6_for_fields(
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str = "",
) -> dict[str, Any]:
    rid = (record_id or "").strip()
    name = (project_name or "").strip() or _field_text(
        fields, config.workflow_project_name_field
    )
    copy_field = str(
        getattr(config, "workflow_kpi6_copy_field", "") or _DEFAULT_COPY_FIELD
    )
    result_field = str(
        getattr(config, "workflow_kpi6_result_field", "") or _DEFAULT_RESULT_FIELD
    )
    wallet = find_wallet_row(token, config, name)
    contract = wallet_contract(wallet[1]) if wallet else ""
    if not contract:
        contract = extract_contract(
            _field_text(fields, "主网合约")
            or _field_text(fields, "Contract Addresss/主网合约")
        )
    window_start = parse_live_start(fields)
    txs: list[dict[str, Any]] = []
    if contract:
        txs = fetch_txlist(contract)
    verdict = evaluate_kpi6(contract=contract, txs=txs, window_start=window_start)
    existing_copy = _field_text(fields, copy_field)
    existing_result = field_result(fields, result_field)
    copy = merge_kpi_copy(existing_copy, str(verdict["copy"]))
    result = merge_kpi_result(existing_result, passed=bool(verdict["passed"]))
    update_record(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        rid,
        {copy_field: copy, result_field: result},
    )
    logger.info(
        "kpi6: %s project=%r record=%s ca=%s wallets=%s txs=%s",
        result,
        name,
        rid,
        contract,
        len(verdict["wallets"]),
        verdict["tx_count"],
    )
    return {
        "result": result,
        "passed": result == _PASS,
        "reason": verdict["reason"],
        "copy": copy,
        "contract": contract,
        "wallets": len(verdict["wallets"]),
        "txs": verdict["tx_count"],
        "project": name,
    }
