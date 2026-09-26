"""KPI 4 / 5: auto-pass once when delivery marks a project mainnet-live.

Does not probe the product, write coordination, or push groups.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import update_record
from bot.workflow_form_chase import field_is_filled

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_KPI4_COPY_FIELD = "KPI 4 - 产品可用验证"
_DEFAULT_KPI4_RESULT_FIELD = "产品可用验证结果"
_DEFAULT_KPI5_COPY_FIELD = "KPI 5 - 项目独立性验证"
_DEFAULT_KPI5_RESULT_FIELD = "独立性验证结果"
_PASS = "通过"
_KPI4_COPY = (
    "产品可用验证，主网mvp上线，能连接钱包，交互合约并消耗 gas，产品可用验证通过"
)
_KPI5_COPY = (
    "项目独立性验证，已经人工验证主网上线并交互产品，独立性验证通过"
)


def kpi45_pass_fields(
    *,
    kpi4_copy_field: str = _DEFAULT_KPI4_COPY_FIELD,
    kpi4_result_field: str = _DEFAULT_KPI4_RESULT_FIELD,
    kpi5_copy_field: str = _DEFAULT_KPI5_COPY_FIELD,
    kpi5_result_field: str = _DEFAULT_KPI5_RESULT_FIELD,
    include_kpi4: bool = True,
    include_kpi5: bool = True,
) -> dict[str, Any]:
    """SingleSelect must be a string, not the read-shape array."""
    payload: dict[str, Any] = {}
    if include_kpi4:
        payload[kpi4_copy_field] = _KPI4_COPY
        payload[kpi4_result_field] = _PASS
    if include_kpi5:
        payload[kpi5_copy_field] = _KPI5_COPY
        payload[kpi5_result_field] = _PASS
    return payload


def _field_names(config: AppConfig) -> tuple[str, str, str, str]:
    return (
        str(getattr(config, "workflow_kpi4_copy_field", "") or _DEFAULT_KPI4_COPY_FIELD),
        str(
            getattr(config, "workflow_kpi4_result_field", "")
            or _DEFAULT_KPI4_RESULT_FIELD
        ),
        str(getattr(config, "workflow_kpi5_copy_field", "") or _DEFAULT_KPI5_COPY_FIELD),
        str(
            getattr(config, "workflow_kpi5_result_field", "")
            or _DEFAULT_KPI5_RESULT_FIELD
        ),
    )


def _state_path(config: AppConfig) -> Path:
    return ROOT / str(
        getattr(config, "workflow_kpi45_state_file", "data/kpi45_live_state.json")
    )


def _load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    results = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(results, dict):
        return {}
    return {str(k): str(v) for k, v in results.items()}


def _save_state(path: Path, results: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fill_kpi45_for_fields(
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str = "",
) -> str:
    """Write KPI 4/5 pass copy + result. Skip filled cells. No fail path."""
    if not getattr(config, "workflow_kpi45_enabled", True):
        return "disabled"
    rid = (record_id or "").strip()
    if not rid:
        return "no_record"
    path = _state_path(config)
    state = _load_state(path)
    if rid in state:
        return f"already:{state[rid]}"

    copy4, result4, copy5, result5 = _field_names(config)
    write_kpi4 = not (
        field_is_filled(fields, copy4) and field_is_filled(fields, result4)
    )
    write_kpi5 = not (
        field_is_filled(fields, copy5) and field_is_filled(fields, result5)
    )
    if not write_kpi4 and not write_kpi5:
        state[rid] = "already_filled"
        _save_state(path, state)
        return "already_filled"

    payload = kpi45_pass_fields(
        kpi4_copy_field=copy4,
        kpi4_result_field=result4,
        kpi5_copy_field=copy5,
        kpi5_result_field=result5,
        include_kpi4=write_kpi4,
        include_kpi5=write_kpi5,
    )
    try:
        update_record(
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            rid,
            payload,
        )
    except Exception:
        logger.exception(
            "kpi45: failed to write pass project=%r record=%s", project_name, rid
        )
        return "write_failed"
    state[rid] = _PASS
    _save_state(path, state)
    logger.info(
        "kpi45: 通过 project=%r record=%s kpi4=%s kpi5=%s",
        project_name,
        rid,
        write_kpi4,
        write_kpi5,
    )
    return _PASS


async def fill_kpi45_for_live_record(
    config: AppConfig,
    token: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str = "",
) -> str:
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: fill_kpi45_for_fields(
            token, config, record_id, fields, project_name=project_name
        ),
    )
