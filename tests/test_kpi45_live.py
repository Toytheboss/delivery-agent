from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from bot.workflow_kpi45_live import (
    _KPI4_COPY,
    _KPI5_COPY,
    fill_kpi45_for_fields,
    kpi45_pass_fields,
)


def test_kpi45_pass_fields_use_string_not_array():
    assert kpi45_pass_fields() == {
        "KPI 4 - 产品可用验证": _KPI4_COPY,
        "产品可用验证结果": "通过",
        "KPI 5 - 项目独立性验证": _KPI5_COPY,
        "独立性验证结果": "通过",
    }


def test_kpi45_copy_is_the_locked_english():
    assert "mainnet MVP is live" in _KPI4_COPY
    assert "wallet can connect" in _KPI4_COPY
    assert _KPI4_COPY.endswith("product availability verification passed")
    assert "manually verified" in _KPI5_COPY
    assert _KPI5_COPY.endswith("independence verification passed")


class _Cfg:
    workflow_kpi45_enabled = True
    workflow_kpi4_copy_field = "KPI 4 - 产品可用验证"
    workflow_kpi4_result_field = "产品可用验证结果"
    workflow_kpi5_copy_field = "KPI 5 - 项目独立性验证"
    workflow_kpi5_result_field = "独立性验证结果"
    workflow_kpi45_state_file = "data/kpi45_live_state.json"
    workflow_base_app_token = "app"
    workflow_progress_table_id = "tbl"


def test_skips_when_both_kpis_already_filled(tmp_path: Path):
    wrote: list[object] = []

    def fake_update(*_args, **_kwargs):
        wrote.append(_args)

    with patch("bot.workflow_kpi45_live.ROOT", tmp_path), patch(
        "bot.workflow_kpi45_live.update_record", fake_update
    ):
        fields = {
            "KPI 4 - 产品可用验证": _KPI4_COPY,
            "产品可用验证结果": ["通过"],
            "KPI 5 - 项目独立性验证": _KPI5_COPY,
            "独立性验证结果": "通过",
        }
        assert (
            fill_kpi45_for_fields("tok", _Cfg(), "rec1", fields, project_name="X")
            == "already_filled"
        )
    assert wrote == []


def test_writes_only_empty_kpi(tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_update(_token, _app, _table, rid, payload):
        captured["rid"] = rid
        captured["payload"] = payload

    with patch("bot.workflow_kpi45_live.ROOT", tmp_path), patch(
        "bot.workflow_kpi45_live.update_record", fake_update
    ):
        fields = {
            "KPI 4 - 产品可用验证": _KPI4_COPY,
            "产品可用验证结果": "通过",
        }
        assert (
            fill_kpi45_for_fields("tok", _Cfg(), "rec2", fields, project_name="X")
            == "通过"
        )
    assert captured["rid"] == "rec2"
    assert captured["payload"] == {
        "KPI 5 - 项目独立性验证": _KPI5_COPY,
        "独立性验证结果": "通过",
    }
