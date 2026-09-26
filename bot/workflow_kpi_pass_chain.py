"""When KPI 1–6 are passed, auto-write KPI 7, coordination, and judgment time.

Used by project diag only (Roy号). Not on the live-status table scan.
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
_FAIL = "不通过"
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


def kpi2_needed(fields: dict[str, Any]) -> bool:
    """Link is in the tracker, but 新闻验证结果 is still empty."""
    return planned_kpi2_result(fields) == _PASS


def planned_kpi2_result(fields: dict[str, Any]) -> str | None:
    """Link → 通过. No link → 不通过. Never downgrade an existing 通过."""
    if field_is_filled(fields, _KPI2_LINK):
        if kpi_cell_passed(fields, _KPI2_RESULT):
            return None
        return _PASS
    current = field_result(fields, _KPI2_RESULT)
    if current in {_PASS, _FAIL}:
        return None
    return _FAIL


def kpi45_needed(fields: dict[str, Any]) -> bool:
    return not kpi_cell_passed(fields, _KPI4_RESULT) or not kpi_cell_passed(
        fields, _KPI5_RESULT
    )


def first_six_passed(fields: dict[str, Any], *, treat_kpi45_as_pass: bool = False) -> bool:
    four_five = treat_kpi45_as_pass or (
        kpi_cell_passed(fields, _KPI4_RESULT)
        and kpi_cell_passed(fields, _KPI5_RESULT)
    )
    return (
        kpi_cell_passed(fields, _KPI1_RESULT)
        and kpi2_passed(fields)
        and kpi_cell_passed(fields, _KPI3_RESULT)
        and four_five
        and kpi_cell_passed(fields, _KPI6_RESULT)
    )


def pass_chain_plan(fields: dict[str, Any], status_field: str = "项目状态") -> dict[str, Any]:
    """What this row still needs. Does not talk to Lark."""
    eligible = diag_not_eligible_reason(fields, status_field) is None
    plan = {
        "write_kpi2": False,
        "write_kpi45": False,
        "write_kpi7": False,
        "write_coord": False,
        "write_time": False,
        "eligible": eligible,
    }
    if eligible and kpi2_needed(fields):
        plan["write_kpi2"] = True
    if eligible and kpi45_needed(fields):
        plan["write_kpi45"] = True
    if coord_is_pass(fields) and not judge_time_filled(fields):
        plan["write_time"] = True
    if coord_is_pass(fields):
        if (
            eligible
            and not kpi_cell_passed(fields, _KPI7_RESULT)
            and first_six_passed(fields, treat_kpi45_as_pass=plan["write_kpi45"])
        ):
            plan["write_kpi7"] = True
        return plan
    if not eligible:
        return plan
    if not first_six_passed(fields, treat_kpi45_as_pass=plan["write_kpi45"]):
        return plan
    if not kpi_cell_passed(fields, _KPI7_RESULT):
        plan["write_kpi7"] = True
    if not coord_is_pass(fields):
        plan["write_coord"] = True
        plan["write_time"] = True
    elif not judge_time_filled(fields):
        plan["write_time"] = True
    return plan


def judge_time_ms(when: Any = None) -> int:
    """Lark datetime cells take epoch milliseconds, not a formatted string."""
    moment = when or now_shanghai()
    return int(moment.timestamp() * 1000)


def write_kpi2_result(token: str, config: Any, record_id: str, result: str) -> None:
    update_record(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        record_id,
        {_KPI2_RESULT: result},
    )


def write_kpi2_pass(token: str, config: Any, record_id: str) -> None:
    write_kpi2_result(token, config, record_id, _PASS)


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
    update_record(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        record_id,
        {_JUDGE_FIELD: judge_time_ms()},
    )


def write_coord_and_time(token: str, config: Any, record_id: str) -> None:
    stamp = judge_time_ms()
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
    if plan["write_kpi2"]:
        write_kpi2_pass(token, config, record_id)
        done.append("kpi2")
        fields = {**fields, _KPI2_RESULT: _PASS}
    if plan["write_kpi45"]:
        from bot.workflow_kpi45_live import fill_kpi45_for_fields

        fill_kpi45_for_fields(token, config, record_id, fields)
        done.append("kpi45")
        fields = {**fields, _KPI4_RESULT: _PASS, _KPI5_RESULT: _PASS}
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
        if not (
            plan["write_kpi2"]
            or plan["write_kpi45"]
            or plan["write_kpi7"]
            or plan["write_coord"]
            or plan["write_time"]
        ):
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
