from __future__ import annotations

from datetime import datetime, timezone, timedelta

from bot.workflow_kpi1_twitter import (
    build_kpi1_copy,
    evaluate_kpi1,
    is_retweet,
    twitter_handle_from_url,
)
from bot.workflow_kpi6_onchain import (
    build_kpi6_copy,
    classify_core_txs,
    evaluate_kpi6,
    is_create_tx,
    unique_wallets,
)
from bot.workflow_kpi_diag import (
    format_project_diag_reply,
    is_kpi_diag_command,
    onchain_fail_note,
    parse_kpi_diag_command,
    twitter_fail_note,
    website_fail_note,
)
from bot.workflow_kpi_write import merge_kpi_copy, merge_kpi_result, parse_live_start


def test_diag_commands_match_plain_text_not_quote():
    assert parse_kpi_diag_command("onchain diag") == "onchain"
    assert parse_kpi_diag_command("twitter diag") == "twitter"
    assert parse_kpi_diag_command("website diag") == "website"
    assert parse_kpi_diag_command("/onchain diag") == "onchain"
    assert parse_kpi_diag_command("website diag!") == "website"
    assert parse_kpi_diag_command("project diag") == "project"
    assert parse_kpi_diag_command("/project diag") == "project"
    assert is_kpi_diag_command("PROJECT DIAG")
    assert is_kpi_diag_command("ONCHAIN DIAG")
    assert not is_kpi_diag_command("pr support")
    assert not is_kpi_diag_command("please onchain diag this")


def test_kpi6_no_contract_copy():
    verdict = evaluate_kpi6(contract="", txs=[], window_start=None)
    assert verdict["passed"] is False
    assert verdict["copy"] == "用户和交互验证，没有检测到合约，用户和交互验证不通过"


def test_kpi6_counts_successful_to_contract_skips_create():
    start = datetime(2026, 9, 26, tzinfo=timezone(timedelta(hours=8)))
    ca = "0xabc0000000000000000000000000000000000001"
    txs = [
        {
            "hash": "c",
            "from": "0x1",
            "to": "",
            "contractAddress": ca,
            "isError": "0",
            "timeStamp": str(int(start.timestamp()) + 10),
        },
        {
            "hash": "f",
            "from": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": ca,
            "contractAddress": "",
            "isError": "1",
            "timeStamp": str(int(start.timestamp()) + 20),
        },
        {
            "hash": "ok1",
            "from": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": ca,
            "contractAddress": "",
            "isError": "0",
            "timeStamp": str(int(start.timestamp()) + 30),
        },
        {
            "hash": "ok2",
            "from": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "to": ca,
            "contractAddress": "",
            "isError": "0",
            "timeStamp": str(int(start.timestamp()) + 40),
        },
        {
            "hash": "old",
            "from": "0xcccccccccccccccccccccccccccccccccccccccc",
            "to": ca,
            "contractAddress": "",
            "isError": "0",
            "timeStamp": str(int(start.timestamp()) - 100),
        },
    ]
    core, skipped = classify_core_txs(txs, contract=ca, window_start=None)
    assert skipped["create"] == 1
    assert skipped["failed"] == 1
    assert skipped["out_window"] == 0
    assert len(core) == 3
    assert unique_wallets(core, ca) == [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "0xcccccccccccccccccccccccccccccccccccccccc",
    ]
    assert is_create_tx(txs[0])
    verdict = evaluate_kpi6(contract=ca, txs=txs, window_start=start)
    assert verdict["tx_count"] == 3
    assert verdict["passed"] is False
    assert "上线日至核查日" not in verdict["copy"]


def test_recheck_appends_and_only_upgrades_pass():
    first = "用户和交互验证，没有检测到合约，用户和交互验证不通过"
    when = datetime(2026, 9, 26, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    merged = merge_kpi_copy(first, "用户和交互验证，独立钱包3个、成功核心交易5笔（门槛≥3钱包且交互≥5笔），独立钱包：0xa、0xb、0xc（此处最多只展示5个独立钱包），用户和交互验证通过", when)
    assert merged.startswith(first)
    assert "复审 2026-09-26 09:30：" in merged
    assert merge_kpi_result("不通过", passed=True) == "通过"
    assert merge_kpi_result("通过", passed=False) == "通过"
    assert merge_kpi_result("", passed=False) == "不通过"


def test_twitter_handle_and_no_account_copy():
    assert twitter_handle_from_url("https://x.com/SubscribeOneHQ") == "SubscribeOneHQ"
    assert twitter_handle_from_url("@OpenLCdev") == "OpenLCdev"
    assert twitter_handle_from_url("https://x.com/i/status/1") == ""
    assert is_retweet("RT @foo hello")
    assert not is_retweet("mainnet is live")
    assert evaluate_kpi1(handle="", count=None, unread=False)["copy"] == (
        "Twitter运营验证，没有检测到官方账号，推特运营验证不通过"
    )
    assert "原发5条" in build_kpi1_copy(handle="Foo", count=5, reason="ok")


def test_live_start_is_shanghai_midnight():
    dt = parse_live_start({"主网上线时间": "2026-09-26T15:33:00+08:00"})
    assert dt is not None
    assert dt.hour == 0
    assert dt.day == 26


def test_project_diag_english_pass_and_fail_copy():
    passed_rows = [
        ("KPI 1 Twitter", True, ""),
        ("KPI 2 PR", True, ""),
        ("KPI 3 Website", True, ""),
        ("KPI 4 Product", True, ""),
        ("KPI 5 Independence", True, ""),
        ("KPI 6 On-chain", True, ""),
    ]
    text = format_project_diag_reply(
        project="Testing", rows=passed_rows, coord_written=True
    )
    assert text.startswith("Project diag for Testing: passed")
    assert "Failed:" not in text
    assert "Coordination: passed" in text
    assert twitter_fail_note({"reason": "below_threshold", "count": 3}) == (
        "3 original posts in 30 days, need ≥5"
    )
    assert onchain_fail_note({"reason": "below_threshold", "wallets": 2, "txs": 4}) == (
        "2 wallets / 4 txs, need ≥3 wallets and ≥5 txs"
    )
    assert website_fail_note({"reason": "no_url"}) == "no site URL"
    failed = format_project_diag_reply(
        project="Testing",
        rows=[
            ("KPI 1 Twitter", False, "3 original posts in 30 days, need ≥5"),
            ("KPI 2 PR", True, ""),
            ("KPI 3 Website", True, ""),
            ("KPI 4 Product", True, ""),
            ("KPI 5 Independence", True, ""),
            ("KPI 6 On-chain", False, "2 wallets / 4 txs, need ≥3 wallets and ≥5 txs"),
        ],
        coord_written=False,
    )
    assert "Project diag for Testing: failed" in failed
    assert "Failed: KPI 1 Twitter, KPI 6 On-chain" in failed
    assert "KPI 1 Twitter: failed (3 original posts in 30 days, need ≥5)" in failed
    assert "Coordination: not written" in failed
