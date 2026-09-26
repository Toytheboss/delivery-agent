"""When KPI 1–6 are passed, auto-write KPI 7, coordination, and judgment time.

Used by project diag and the live-status-watch table scan (Roy号 only).
"""

from __future__ import annotations

import logging
from typing import Any

from bot.lark_bitable import update_record
from bot.workflow_form_chase import field_is_filled
from bot.workflow_form_dispatch import _field_text
from bot.workflow_kpi_write import (
    diag_not_eligible_reason,
    field_result,
    merge_kpi_copy,
    now_shanghai,
)

logger = logging.getLogger(__name__)

_PASS = "通过"
_COORD_PASS_VALUES = frozenset({_PASS, "有效 KPI"})
_COORD_FIELD = "KPI 统筹"
_JUDGE_FIELD = "KPI 判定时间"
_KPI1_RESULT = "推特验证结果"
_KPI2_LINK = "KPI 2 - PR 新闻链接验证"
_KPI2_RESULT = "新闻验证结果"
_KPI3_RESULT = "官网验证结果"
_KPI4_RESULT = "产品可用验证结果"
_KPI5_RESULT = "独立性验证结果"
_KPI6_RESULT = "交互验证结果"
_KPI7_RESULT = "持续运营要求验证结果"
_KPI7_COPY_FIELD = "KPI 7 - 持续运营要求验证"
KPI7_PASS_COPY = (
    "Ongoing operations verification: website and product were reachable on the "
    "check day; Twitter, community and product all have ongoing updates; "
    "ongoing operations verification passed"
)


def kpi_cell_passed(fields: dict[str, Any], result_field: str) -> bool:
    return field_result(fields, result_field) == _PASS


def coord_is_pass(fields: dict[str, Any]) -> bool:
    return field_result(fields, _COORD_FIELD) in _COORD_PASS_VALUES


def judge_time_filled(fields: dict[str, Any]) -> bool:
    if field_is_filled(fields, _JUDGE_FIELD):
        return True
    return bool((_field_text(fields, _JUDGE_FIELD) or "").strip())


def kpi2_passed(fields: dict[str, Any]) -> bool:
    return kpi_cell_passed(fields, _KPI2_RESULT) or field_is_filled(fields, _KPI2_LINK)


def first_six_passed(fields: dict[str, Any]) -> bool:
    return (
        kpi_cell_passed(fields, _KPI1_RESULT)
        and kpi2_passed(fields)
        and kpi_cell_passed(fields, _KPI3_RESULT)
        and kpi_cell_passed(fields, _KPI4_RESULT)
        and kpi_cell_passed(fields, _KPI5_RESULT)
        and kpi_cell_passed(fields, _KPI6_RESULT)
    )


def pass_chain_plan(fields: dict[str, Any], status_field: str = "项目状态") -> dict[str, Any]:
    """What this row still needs. Does not talk to Lark."""
    plan = {
        "write_kpi7": False,
        "write_coord": False,
        "write_time": False,
        "eligible": diag_not_eligible_reason(fields, status_field) is None,
    }
    if coord_is_pass(fields) and not judge_time_filled(fields):
        plan["write_time"] = True
        return plan
    if not plan["eligible"]:
        return plan
    if not first_six_passed(fields):
        return plan
    if not kpi_cell_passed(fields, _KPI7_RESULT):
        plan["write_kpi7"] = True
    if not coord_is_pass(fields):
        plan["write_coord"] = True
        plan["write_time"] = True
    elif not judge_time_filled(fields):
        plan["write_time"] = True
    return plan


def _stamp() -> str:
    return now_shanghai().strftime("%Y-%m-%d %H:%M")


def write_kpi7_pass(
    token: str, config: Any, record_id: str, existing_copy: str = ""
) -> None:
    update_record(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        record_id,
        {
            _KPI7_COPY_FIELD: merge_kpi_copy(existing_copy, KPI7_PASS_COPY),
            _KPI7_RESULT: _PASS,
        },
    )


def write_judge_time(token: str, config: Any, record_id: str) -> None:
    stamp = _stamp()
    update_record(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        record_id,
        {_JUDGE_FIELD: stamp},
    )


def write_coord_and_time(token: str, config: Any, record_id: str) -> None:
    stamp = _stamp()
    last_error: Exception | None = None
    for coord in (_PASS, "有效 KPI"):
        try:
            update_record(
                token,
                config.workflow_base_app_token,
                config.workflow_progress_table_id,
                record_id,
                {_COORD_FIELD: coord, _JUDGE_FIELD: stamp},
            )
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error:
        update_record(
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            record_id,
            {_COORD_FIELD: "有效 KPI"},
        )
        try:
            write_judge_time(token, config, record_id)
        except Exception:
            logger.exception("kpi pass-chain: judge time write failed record=%s", record_id)


def apply_pass_chain(
    token: str,
    config: Any,
    record_id: str,
    fields: dict[str, Any],
) -> list[str]:
    status_field = str(getattr(config, "workflow_status_field", "") or "项目状态")
    plan = pass_chain_plan(fields, status_field)
    done: list[str] = []
    if plan["write_kpi7"]:
        write_kpi7_pass(token, config, record_id, _field_text(fields, _KPI7_COPY_FIELD))
        done.append("kpi7")
        fields = {**fields, _KPI7_RESULT: _PASS}
    if plan["write_coord"]:
        write_coord_and_time(token, config, record_id)
        done.append("coord")
        done.append("time")
        return done
    if plan["write_time"]:
        write_judge_time(token, config, record_id)
        done.append("time")
    return done


def apply_pass_chain_records(
    token: str,
    config: Any,
    records: list[dict[str, Any]],
) -> int:
    wrote = 0
    for row in records:
        rid = str(row.get("record_id") or "").strip()
        fields = row.get("fields") or {}
        if not rid or not isinstance(fields, dict):
            continue
        plan = pass_chain_plan(
            fields, str(getattr(config, "workflow_status_field", "") or "项目状态")
        )
        if not (plan["write_kpi7"] or plan["write_coord"] or plan["write_time"]):
            continue
        try:
            done = apply_pass_chain(token, config, rid, fields)
        except Exception:
            logger.exception("kpi pass-chain failed record=%s", rid)
            continue
        if done:
            wrote += 1
            logger.info("kpi pass-chain %s record=%s", ",".join(done), rid)
    return wrote
