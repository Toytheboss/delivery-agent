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
    format_tg_check_reply,
    is_kpi_diag_command,
    onchain_fail_note,
    parse_kpi_diag_command,
    project_diag_audits_to_run,
    twitter_fail_note,
    website_fail_note,
    _reply_for,
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
    assert "Contract: not submitted" in verdict["copy"]
    assert verdict["copy"].endswith("- Result: failed")


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
    assert "Meets the audit requirement" not in verdict["copy"]
    assert "Tx hashes:" in verdict["copy"]
    assert "ok1" in verdict["copy"]
    assert "ok2" in verdict["copy"]
    assert "old" in verdict["copy"]


def test_wallet_row_keeps_both_contracts():
    from bot.workflow_kpi_write import wallet_contracts

    first = "0x" + ("11" * 20)
    second = "0x" + ("22" * 20)
    tx = "0x" + ("33" * 32)
    assert wallet_contracts(
        {"Mainnet Contract Addresss": f"{first}\n{tx}\n{second}"}
    ) == [first, second]


def test_kpi6_combines_two_contracts():
    from bot.workflow_kpi6_onchain import evaluate_kpi6_contracts

    start = datetime(2026, 9, 26, tzinfo=timezone(timedelta(hours=8)))
    first = "0xabc0000000000000000000000000000000000001"
    second = "0xabc0000000000000000000000000000000000002"
    senders = [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "0xcccccccccccccccccccccccccccccccccccccccc",
    ]

    def tx(hash_id: str, sender: str, ca: str, offset: int) -> dict:
        return {
            "hash": hash_id,
            "from": sender,
            "to": ca,
            "contractAddress": "",
            "isError": "0",
            "timeStamp": str(int(start.timestamp()) + offset),
        }

    verdict = evaluate_kpi6_contracts(
        contracts=[first, second],
        txs_by_contract={
            first: [tx("a1", senders[0], first, 1), tx("a2", senders[0], first, 2)],
            second: [
                tx("b1", senders[1], second, 3),
                tx("b2", senders[1], second, 4),
                tx("b3", senders[2], second, 5),
            ],
        },
    )
    assert verdict["passed"] is True
    assert verdict["tx_count"] == 5
    assert set(verdict["wallets"]) == set(senders)


def test_kpi6_pass_lists_three_wallets_and_five_hashes():
    start = datetime(2026, 9, 26, tzinfo=timezone(timedelta(hours=8)))
    ca = "0xabc0000000000000000000000000000000000001"
    txs = []
    senders = [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "0xcccccccccccccccccccccccccccccccccccccccc",
        "0xdddddddddddddddddddddddddddddddddddddddd",
    ]
    for i in range(7):
        txs.append(
            {
                "hash": f"h{i}",
                "from": senders[i % 4],
                "to": ca,
                "contractAddress": "",
                "isError": "0",
                "timeStamp": str(int(start.timestamp()) + i + 1),
            }
        )
    verdict = evaluate_kpi6(contract=ca, txs=txs, window_start=start)
    assert verdict["passed"] is True
    assert verdict["tx_count"] == 7
    assert "Meets the audit requirement" in verdict["copy"]
    assert verdict["copy"].count("0x") >= 3
    listed_hashes = [
        line.strip() for line in verdict["copy"].splitlines() if line.strip().startswith("h")
    ]
    assert listed_hashes == ["h6", "h5", "h4", "h3", "h2"]
    wallet_block = verdict["copy"].split("Wallets:")[1].split("Tx hashes:")[0]
    wallet_lines = [ln.strip() for ln in wallet_block.splitlines() if ln.strip().startswith("0x")]
    assert len(wallet_lines) == 3


def test_new_check_log_stamps_every_round():
    when = datetime(2026, 9, 30, 17, 24, tzinfo=timezone(timedelta(hours=8)))
    first = merge_kpi_copy(
        "",
        "- Site opened: yes\n- https://botchain.ai: no\n- Result: failed",
        when,
    )
    assert first.startswith("First check 2026-09-30 17:24\n")
    second = merge_kpi_copy(
        first,
        "- Site opened: yes\n- https://botchain.ai: yes\n- Result: passed",
        datetime(2026, 9, 30, 18, 0, tzinfo=timezone(timedelta(hours=8))),
    )
    assert "\nRecheck 2026-09-30 18:00\n" in second
    assert second.startswith("First check 2026-09-30 17:24\n")
    text = format_tg_check_reply(
        label="Website",
        project="Relay",
        result="passed",
        copy=second,
        kind="website",
    )
    assert text.count("- Site opened: yes") == 2
    assert "First check 2026-09-30 17:24" in text
    assert "Recheck 2026-09-30 18:00" in text


def test_recheck_appends_and_only_upgrades_pass():
    first = "User and interaction verification: no contract detected; user and interaction verification failed"
    when = datetime(2026, 9, 26, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    merged = merge_kpi_copy(
        first,
        "User and interaction verification: 3 unique wallets, 5 successful core txs (threshold ≥3 wallets and ≥5 txs); unique wallets: 0xa, 0xb, 0xc (at most 5 unique wallets shown here); user and interaction verification passed",
        when,
    )
    assert merged.startswith(first)
    assert "\nRecheck 2026-09-26 09:30\n" in merged
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
        "- Official account: not submitted\n- Result: failed"
    )
    assert "Original posts (30d): 5 (need ≥5)" in build_kpi1_copy(
        handle="Foo", count=5, reason="ok"
    )
    below = build_kpi1_copy(
        handle="Foo",
        count=3,
        reason="ok",
        links=[
            "https://x.com/Foo/status/1",
            "https://x.com/Foo/status/2",
            "https://x.com/Foo/status/3",
        ],
    )
    assert "Meets the audit requirement" not in below
    assert below.endswith(
        "- https://x.com/Foo/status/1\n"
        "- https://x.com/Foo/status/2\n"
        "- https://x.com/Foo/status/3"
    )
    copy = build_kpi1_copy(
        handle="Foo",
        count=7,
        reason="ok",
        links=[f"https://x.com/Foo/status/{i}" for i in range(1, 8)],
    )
    assert "Meets the audit requirement" in copy
    assert "https://x.com/Foo/status/5" in copy
    assert "https://x.com/Foo/status/6" not in copy


def test_live_start_is_shanghai_midnight():
    dt = parse_live_start({"主网上线时间": "2026-09-26T15:33:00+08:00"})
    assert dt is not None
    assert dt.hour == 0
    assert dt.day == 26


def test_project_diag_english_pass_and_fail_copy():
    passed_rows = [
        ("Twitter", True, "Twitter operations verification: already passed"),
        ("News/PR", True, "News/PR verification: a news URL was submitted; news/PR verification passed"),
        ("Website", True, "Website display verification: already passed"),
        ("Product", True, "Product availability verification: mainnet MVP is live; wallet can connect, interact with the contract and consume gas; product availability verification passed"),
        ("Independence", True, "Independence verification: mainnet go-live and product interaction have been manually verified; independence verification passed"),
        ("On-chain", True, "User and interaction verification: already passed"),
        ("Ongoing operations", True, "Ongoing operations verification: website and product were reachable on the check day; Twitter, community and product all have ongoing updates; ongoing operations verification passed"),
    ]
    text = format_project_diag_reply(
        project="Testing", rows=passed_rows, coord_written=True
    )
    assert text.startswith("Project diag · Testing · passed")
    assert "Failed" not in text.split("Passed")[0]
    assert "Final evaluation: passed" in text
    assert "KPI" not in text
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
                "Twitter",
                False,
                "Twitter operations verification: official account could not be "
                "read for original posts in the last 30 days; "
                "Twitter operations verification failed",
            ),
            ("News/PR", True, "News/PR verification: a news URL was submitted; news/PR verification passed"),
            (
                "Website",
                False,
                "Website display verification: no official website URL submitted; "
                "website display verification failed",
            ),
            ("Product", True, "Product availability verification: mainnet MVP is live; wallet can connect, interact with the contract and consume gas; product availability verification passed"),
            ("Independence", True, "Independence verification: mainnet go-live and product interaction have been manually verified; independence verification passed"),
            ("On-chain", True, "User and interaction verification: already passed"),
            (
                "Ongoing operations",
                False,
                "Ongoing operations verification: not passed (earlier checks still have open items)",
            ),
        ],
        coord_written=False,
    )
    assert "Project diag · Testing · failed" in failed
    assert failed.index("Failed") < failed.index("Passed")
    assert "\nTwitter\n" in failed
    assert "Original posts (30d): unread" in failed
    assert "Official website URL: not submitted" in failed
    assert "- Result: failed" in failed
    assert "KPI" not in failed
    assert "Final evaluation: not written" in failed
    skipped = format_project_diag_reply(
        project="Testing", rows=[], coord_written=True, skipped=True
    )
    assert "skipped" in skipped
    assert "Final evaluation already passed" in skipped


def test_tg_check_reply_splits_rechecks_not_lark_blob():
    first = (
        "Website display verification: website opened, BOT Chain name is visible, "
        "no clickable https://botchain.ai or https://scan.botchain.ai; "
        "website display verification failed"
    )
    when = datetime(2026, 9, 28, 17, 33, tzinfo=timezone(timedelta(hours=8)))
    second = (
        "Website display verification: website opened, BOT Chain name is visible, "
        "has clickable https://botchain.ai, but no clickable https://scan.botchain.ai; "
        "website display verification failed"
    )
    third = (
        "Website display verification: website opened, BOT Chain name is visible, "
        "page has clickable https://botchain.ai and https://scan.botchain.ai; "
        "website display verification passed"
    )
    copy = merge_kpi_copy(first, second, when)
    copy = merge_kpi_copy(
        copy,
        third,
        datetime(2026, 9, 29, 0, 8, tzinfo=timezone(timedelta(hours=8))),
    )
    text = format_tg_check_reply(
        label="Website",
        project="Relay",
        result="passed",
        copy=copy,
        kind="website",
    )
    assert text.startswith("Website · Relay · passed")
    assert "First check" in text
    assert "Recheck 2026-09-28 17:33" in text
    assert "Recheck 2026-09-29 00:08" in text
    assert "written for" not in text
    assert "website display verification:" not in text.lower()
    first_block, after_first = text.split("First check", 1)
    del first_block
    round1, rest = after_first.split("Recheck 2026-09-28 17:33", 1)
    round2, round3 = rest.split("Recheck 2026-09-29 00:08", 1)
    assert "- Site opened: yes" in round1
    assert "- BOT Chain name: yes" in round1
    assert "- https://botchain.ai: no" in round1
    assert "- https://scan.botchain.ai: no" in round1
    assert "- Result: failed" in round1
    assert "- https://botchain.ai: yes" in round2
    assert "- https://scan.botchain.ai: no" in round2
    assert "- Result: failed" in round2
    assert "- https://botchain.ai: yes" in round3
    assert "- https://scan.botchain.ai: yes" in round3
    assert "- Result: passed" in round3
    twitter = _reply_for(
        "twitter",
        {
            "project": "SubscribeOne",
            "result": "不通过",
            "copy": merge_kpi_copy(
                "Twitter operations verification: no official account submitted; "
                "Twitter operations verification failed",
                "Twitter operations verification: official account @Foo posted 3 "
                "original posts in the last 30 days (threshold ≥5); "
                "Twitter operations verification failed",
                datetime(2026, 9, 26, 9, 30, tzinfo=timezone(timedelta(hours=8))),
            ),
        },
    )
    assert twitter.startswith("Twitter · SubscribeOne · failed")
    assert "Official account: not submitted" in twitter
    assert "Official account: @Foo" in twitter
    assert "Original posts (30d): 3 (need ≥5)" in twitter
    onchain = format_tg_check_reply(
        label="On-chain",
        project="Testing",
        result="failed",
        copy=(
            "User and interaction verification: no contract detected; "
            "user and interaction verification failed"
        ),
        kind="onchain",
    )
    assert "Contract: not submitted" in onchain
    assert "First check" in onchain


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
    from bot.workflow_kpi_pass_chain import pass_chain_plan, planned_kpi2_result

    live = {
        "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
        "主网上线时间": "2026-09-01T00:10:00+08:00",
        "KPI 2 - PR 新闻链接验证": "https://x.com/SprayMe/status/1",
    }
    plan = pass_chain_plan(live)
    assert plan["write_kpi2"] is True
    assert planned_kpi2_result(live) == "通过"
    live["新闻验证结果"] = "通过"
    plan = pass_chain_plan(live)
    assert plan["write_kpi2"] is False
    plan = pass_chain_plan({"项目状态": "对接中", "KPI 2 - PR 新闻链接验证": "https://x.com/x/status/1"})
    assert plan["write_kpi2"] is False


def test_project_diag_kpi2_fail_when_no_pr_link():
    from bot.workflow_kpi_pass_chain import planned_kpi2_result

    assert planned_kpi2_result({}) == "不通过"
    assert planned_kpi2_result({"新闻验证结果": "不通过"}) is None
    assert planned_kpi2_result({"新闻验证结果": "通过"}) is None
    assert (
        planned_kpi2_result(
            {
                "KPI 2 - PR 新闻链接验证": "https://x.com/x/status/1",
                "新闻验证结果": "不通过",
            }
        )
        == "通过"
    )


def test_judge_time_is_epoch_milliseconds():
    from datetime import datetime, timedelta, timezone

    from bot.workflow_kpi_pass_chain import judge_time_ms

    when = datetime(2026, 9, 26, 12, 41, tzinfo=timezone(timedelta(hours=8)))
    assert judge_time_ms(when) == int(when.timestamp() * 1000)
    assert isinstance(judge_time_ms(when), int)


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

