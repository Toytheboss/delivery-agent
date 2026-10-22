from __future__ import annotations

from bot.workflow_form_dispatch import _field_text, field_key, field_raw
from bot.workflow_kpi_write import parse_live_start
from bot.workflow_live_link_sync import live_link_empty


def test_field_raw_reads_old_or_new_label():
    old = {"项目状态": "BOT主网上线 Live on BOT Chain Mainnet"}
    new = {"项目状态 Project Status": "BOT主网上线 Live on BOT Chain Mainnet"}
    assert field_raw(old, "项目状态") == old["项目状态"]
    assert field_raw(old, "项目状态 Project Status") == old["项目状态"]
    assert field_raw(new, "项目状态") == new["项目状态 Project Status"]
    assert field_raw(new, "项目状态 Project Status") == new["项目状态 Project Status"]
    assert _field_text(new, "项目状态").startswith("BOT主网上线")


def test_field_key_keeps_existing_then_defaults_to_new():
    old = {"已上线链接🔗": ""}
    new = {"已上线链接🔗 Project Website URL": ""}
    assert field_key(old, "已上线链接🔗") == "已上线链接🔗"
    assert field_key(old, "已上线链接🔗 Project Website URL") == "已上线链接🔗"
    assert field_key(new, "已上线链接🔗") == "已上线链接🔗 Project Website URL"
    assert field_key({}, "已上线链接🔗") == "已上线链接🔗 Project Website URL"
    assert field_key({}, "项目状态") == "项目状态 Project Status"


def test_parse_live_start_and_live_link_alias():
    ms = 1_766_044_800_000
    assert parse_live_start({"主网上线时间 Mainnet Launch Date": ms}) is not None
    assert live_link_empty(
        {"已上线链接🔗 Project Website URL": ""}, "已上线链接🔗"
    )
    assert not live_link_empty(
        {"已上线链接🔗 Project Website URL": {"link": "https://a.example/"}},
        "已上线链接🔗",
    )
