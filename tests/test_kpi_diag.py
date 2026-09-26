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
    already_passed,
    format_project_diag_reply,
    is_kpi_diag_command,
    onchain_fail_note,
    parse_kpi_diag_command,
    project_diag_audits_to_run,
    twitter_fail_note,
    website_fail_note,
)
from bot.workflow_kpi_write import (
    diag_not_eligible_reason,
    merge_kpi_copy,
    merge_kpi_result,
    parse_live_start,
)


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
    assert "no contract detected" in verdict["copy"]


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
    first = "User and interaction verification: no contract detected; user and interaction verification failed"
    when = datetime(2026, 9, 26, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    merged = merge_kpi_copy(
        first,
        "User and interaction verification: 3 unique wallets, 5 successful core txs (threshold ≥3 wallets and ≥5 txs); unique wallets: 0xa, 0xb, 0xc (at most 5 unique wallets shown here); user and interaction verification passed",
        when,
    )
    assert merged.startswith(first)
    assert "Recheck 2026-09-26 09:30:" in merged
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
        "Twitter operations verification: no official account submitted; "
        "Twitter operations verification failed"
    )
    assert "posted 5 original posts" in build_kpi1_copy(handle="Foo", count=5, reason="ok")


def test_live_start_is_shanghai_midnight():
    dt = parse_live_start({"主网上线时间": "2026-09-26T15:33:00+08:00"})
    assert dt is not None
    assert dt.hour == 0
    assert dt.day == 26


def test_project_diag_english_pass_and_fail_copy():
    passed_rows = [
        ("KPI 1 Twitter", True, "Twitter operations verification: already passed"),
        ("KPI 2 PR", True, "News/PR verification: a news URL was submitted; news/PR verification passed"),
        ("KPI 3 Website", True, "Website display verification: already passed"),
        ("KPI 4 Product", True, "Product availability verification: mainnet MVP is live; wallet can connect, interact with the contract and consume gas; product availability verification passed"),
        ("KPI 5 Independence", True, "Independence verification: mainnet go-live and product interaction have been manually verified; independence verification passed"),
        ("KPI 6 On-chain", True, "User and interaction verification: already passed"),
        ("KPI 7 Ongoing", True, "Ongoing operations verification: website and product were reachable on the check day; Twitter, community and product all have ongoing updates; ongoing operations verification passed"),
    ]
    text = format_project_diag_reply(
        project="Testing", rows=passed_rows, coord_written=True
    )
    assert text.startswith("Project diag for Testing: passed")
    assert "Failed" not in text.split("Passed")[0]
    assert "Final evaluation: passed" in text
    assert twitter_fail_note({"reason": "below_threshold", "count": 3}) == (
        "Twitter operations verification: official account posted 3 "
        "original posts in the last 30 days (threshold ≥5); "
        "Twitter operations verification failed"
    )
    assert "2 unique wallets" in onchain_fail_note(
        {"reason": "below_threshold", "wallets": 2, "txs": 4}
    )
    assert "no official website URL submitted" in website_fail_note({"reason": "no_url"})
    failed = format_project_diag_reply(
        project="Testing",
        rows=[
            (
                "KPI 1 Twitter",
                False,
                "Twitter operations verification: official account could not be "
                "read for original posts in the last 30 days; "
                "Twitter operations verification failed",
            ),
            ("KPI 2 PR", True, "News/PR verification: a news URL was submitted; news/PR verification passed"),
            (
                "KPI 3 Website",
                False,
                "Website display verification: no official website URL submitted; "
                "website display verification failed",
            ),
            ("KPI 4 Product", True, "Product availability verification: mainnet MVP is live; wallet can connect, interact with the contract and consume gas; product availability verification passed"),
            ("KPI 5 Independence", True, "Independence verification: mainnet go-live and product interaction have been manually verified; independence verification passed"),
            ("KPI 6 On-chain", True, "User and interaction verification: already passed"),
            (
                "KPI 7 Ongoing",
                False,
                "Ongoing operations verification: not passed (KPI 1–6 still have open items)",
            ),
        ],
        coord_written=False,
    )
    assert "Project diag for Testing: failed" in failed
    assert failed.index("Failed") < failed.index("Passed")
    assert "KPI 1 Twitter:" in failed
    assert "Final evaluation: not written" in failed
    skipped = format_project_diag_reply(
        project="Testing", rows=[], coord_written=True, skipped=True
    )
    assert "skipped" in skipped
    assert "Final evaluation already passed" in skipped


def test_project_diag_skips_already_passed_audits():
    assert already_passed({"推特验证结果": "通过"}, "推特验证结果")
    assert not already_passed({"推特验证结果": "不通过"}, "推特验证结果")
    assert not already_passed({}, "推特验证结果")
    fields = {
        "推特验证结果": "通过",
        "官网验证结果": "通过",
        "交互验证结果": "不通过",
    }
    assert project_diag_audits_to_run(fields) == ["onchain"]
    all_pass = {
        "推特验证结果": "通过",
        "官网验证结果": "通过",
        "交互验证结果": "通过",
    }
    assert project_diag_audits_to_run(all_pass) == []
    assert project_diag_audits_to_run({}) == ["twitter", "website", "onchain"]


def test_diag_requires_live_on_or_after_sept_2026():
    assert diag_not_eligible_reason({"项目状态": "对接中"}) == (
        "This project is not marked mainnet-live yet."
    )
    assert diag_not_eligible_reason(
        {
            "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
            "主网上线时间": "2026-08-31T12:00:00+08:00",
        }
    ) == (
        "This command only runs for projects that went live on mainnet "
        "on or after 2026-09-01."
    )
    assert (
        diag_not_eligible_reason(
            {
                "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                "主网上线时间": "2026-09-01T00:10:00+08:00",
            }
        )
        is None
    )


def test_pass_chain_plan_six_pass_then_seven_coord_time():
    from bot.workflow_kpi_pass_chain import pass_chain_plan

    live = {
        "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
        "主网上线时间": "2026-09-01T00:10:00+08:00",
        "推特验证结果": "通过",
        "新闻验证结果": "通过",
        "官网验证结果": "通过",
        "产品可用验证结果": "通过",
        "独立性验证结果": "通过",
        "交互验证结果": "通过",
    }
    plan = pass_chain_plan(live)
    assert plan["write_kpi7"] is True
    assert plan["write_coord"] is True
    assert plan["write_time"] is True
    live["持续运营要求验证结果"] = "通过"
    plan = pass_chain_plan(live)
    assert plan["write_kpi7"] is False
    assert plan["write_coord"] is True
    assert plan["write_time"] is True
    live["KPI 统筹"] = "有效 KPI"
    plan = pass_chain_plan(live)
    assert plan["write_kpi7"] is False
    assert plan["write_coord"] is False
    assert plan["write_time"] is True
    live["KPI 判定时间"] = "2026-09-26 11:00"
    plan = pass_chain_plan(live)
    assert plan["write_time"] is False


def test_pass_chain_fills_empty_kpi45_on_live_project():
    from bot.workflow_kpi_pass_chain import pass_chain_plan

    fields = {
        "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
        "主网上线时间": "2026-09-01T00:10:00+08:00",
        "KPI 统筹": "有效 KPI",
    }
    plan = pass_chain_plan(fields)
    assert plan["write_kpi45"] is True
    assert plan["write_time"] is True


def test_pass_chain_writes_kpi2_when_pr_link_exists():
    from bot.workflow_kpi_pass_chain import pass_chain_plan

    live = {
        "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
        "主网上线时间": "2026-09-01T00:10:00+08:00",
        "KPI 2 - PR 新闻链接验证": "https://x.com/SprayMe/status/1",
    }
    plan = pass_chain_plan(live)
    assert plan["write_kpi2"] is True
    live["新闻验证结果"] = "通过"
    plan = pass_chain_plan(live)
    assert plan["write_kpi2"] is False
    plan = pass_chain_plan({"项目状态": "对接中", "KPI 2 - PR 新闻链接验证": "https://x.com/x/status/1"})
    assert plan["write_kpi2"] is False


def test_pass_chain_stamps_time_when_coord_already_passed():
    from bot.workflow_kpi_pass_chain import pass_chain_plan

    fields = {
        "项目状态": "对接中",
        "KPI 统筹": ["通过"],
    }
    plan = pass_chain_plan(fields)
    assert plan["write_time"] is True
    assert plan["write_kpi7"] is False
    assert plan["write_coord"] is False

