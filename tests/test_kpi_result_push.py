from datetime import datetime, timezone

from bot.workflow_kpi_result_push import (
    audit_first_check,
    format_result_post,
    is_september_2026_live,
    onchain_line_from_copy,
    onchain_post_line,
    pending_september_rows,
    pr_post_line,
    twitter_line_from_copy,
    twitter_post_line,
    website_fix,
)


def test_twitter_and_onchain_lines():
    assert twitter_post_line(handle="", count=None, unread=False) == (
        False,
        "Not submitted",
    )
    assert twitter_post_line(handle="demo", count=2, unread=False)[1] == (
        "`2` original posts. Does not meet the Twitter requirement."
    )
    assert twitter_post_line(handle="demo", count=7, unread=False)[0] is True
    assert onchain_post_line(contract="", wallets=0, txs=0) == (False, "Not submitted")
    assert "0" not in onchain_post_line(contract="", wallets=0, txs=0)[1]
    short = onchain_post_line(contract="0xabc", wallets=2, txs=4)[1]
    assert short.startswith("`2` wallets, `4` txs.")
    assert "Does not meet" in short


def test_pr_line_keeps_status_url():
    ok, url = pr_post_line("https://x.com/demo/status/20?s=20")
    assert ok is True
    assert url == "https://x.com/demo/status/20"
    assert pr_post_line("") == (False, "Not submitted")


def test_website_fix_names_missing_links():
    both = (
        "Website display verification: website opened, BOT Chain name is visible, "
        "no clickable https://botchain.ai or https://scan.botchain.ai; "
        "website display verification failed"
    )
    assert "https://botchain.ai and https://scan.botchain.ai" in website_fix(
        "missing_official_link", both
    )
    one = (
        "Website display verification: website opened, BOT Chain name is visible, "
        "has clickable https://scan.botchain.ai, but no clickable https://botchain.ai; "
        "website display verification failed"
    )
    fix = website_fix("missing_official_link", one)
    assert "https://botchain.ai" in fix
    assert "and https://scan.botchain.ai" not in fix


def test_held_post_omits_kpi7_and_lists_only_the_failed_fix():
    text = format_result_post(
        project="doubledouble",
        bd_name="Daniel",
        bd_open_id="ou_bd",
        live_date="2026-09-14",
        check_date="2026-09-30",
        twitter_ok=True,
        twitter_line="`7` original posts. Meets the Twitter requirement.",
        pr_ok=False,
        pr_line="Not submitted",
        website_ok=True,
        website_line="Website display verification: website display verification passed",
        onchain_ok=True,
        onchain_line="`6` wallets, `7` txs. Meets the wallet and on-chain requirement.",
        fixes=["share the Twitter PR link in the Telegram group"],
    )
    assert text.startswith('<at user_id="ou_bd">Daniel</at>')
    assert "**Result:** Held for rectification" in text
    assert "**Result:** KPI failed" not in text
    assert "KPI 7" not in text
    assert text.index("**Failed**") < text.index("**Passed**")
    assert "**KPI 2 PR:** Not submitted" in text
    assert "Any successful submit triggers a **final** recheck now" in text
    assert "live day `21`" in text
    assert "share the Twitter PR link" not in text
    assert "within `2` weeks" not in text
    assert "Day `1`" in text


def test_valid_post_includes_kpi7_and_the_fixed_summary():
    text = format_result_post(
        project="example",
        bd_name="Ada",
        bd_open_id="ou_ada",
        live_date="2026-09-02",
        check_date="2026-09-30",
        twitter_ok=True,
        twitter_line="`5` original posts. Meets the Twitter requirement.",
        pr_ok=True,
        pr_line="https://x.com/example/status/1",
        website_ok=True,
        website_line="Website display verification: website display verification passed",
        onchain_ok=True,
        onchain_line="`3` wallets, `5` txs. Meets the wallet and on-chain requirement.",
        fixes=[],
    )
    assert "**Result:** Valid KPI" in text
    assert "KPI 7 Ongoing operations" in text
    assert "ongoing operations verification passed" in text
    assert "This is a valid KPI. There is no rectification item." in text
    assert "**Failed**" not in text
    assert "mainnet MVP is live" in text
    assert "independence verification passed" in text


def test_final_fail_post_is_not_a_hold():
    text = format_result_post(
        project="example",
        bd_name="Ada",
        bd_open_id="ou_ada",
        live_date="2026-10-01",
        check_date="2026-10-22",
        twitter_ok=False,
        twitter_line="`2` original posts. Does not meet the Twitter requirement.",
        pr_ok=True,
        pr_line="https://x.com/example/status/1",
        website_ok=True,
        website_line="Website display verification: website display verification passed",
        onchain_ok=True,
        onchain_line="`3` wallets, `5` txs. Meets the wallet and on-chain requirement.",
        fixes=[],
        final=True,
        final_trigger="calendar",
        first_check_date="2026-10-08",
    )
    assert "**First check:** `2026-10-08` · Held for rectification" in text
    assert "**Second check:** `2026-10-22` · Day `21` recheck" in text
    assert "**Result:** KPI failed" in text
    assert "KPI 7" not in text
    assert "no further fix window" in text


def test_submit_triggered_final_label():
    text = format_result_post(
        project="example",
        bd_name="Ada",
        bd_open_id="ou_ada",
        live_date="2026-10-01",
        check_date="2026-10-10",
        twitter_ok=True,
        twitter_line="`5` original posts. Meets the Twitter requirement.",
        pr_ok=True,
        pr_line="https://x.com/example/status/1",
        website_ok=False,
        website_line="Result: failed",
        onchain_ok=True,
        onchain_line="`3` wallets, `5` txs. Meets the wallet and on-chain requirement.",
        fixes=[],
        final=True,
        final_trigger="submit",
        first_check_date="2026-10-08",
    )
    assert "**First check:** `2026-10-08` · Held for rectification" in text
    assert "**Second check:** `2026-10-10` · final (triggered by submit)" in text
    assert "**Result:** KPI failed" in text
    assert "`KPI failed` under the new standard" in text


def test_first_check_date_prefers_sept30_cell_stamp_over_live_plus_7():
    from bot.workflow_kpi_result_push import resolve_first_check_date

    fields = {
        "KPI 3 - 官网展示验证": (
            "Website display verification failed\n"
            "Recheck 2026-09-30 03:26: Website display verification failed"
        )
    }
    assert (
        resolve_first_check_date(
            "2026-09-04",
            first_check_date="2026-10-09",
            fields=fields,
        )
        == "2026-09-30"
    )
    assert resolve_first_check_date("2026-09-04", first_check_date="") == "2026-09-11"


def test_website_post_line_is_one_line_not_checklist():
    from bot.workflow_kpi_result_push import website_post_line

    raw = (
        "- Site opened: yes\n"
        "- BOT Chain name: yes\n"
        "- https://botchain.ai: yes\n"
        "- https://scan.botchain.ai: yes\n"
        "- Result: passed"
    )
    line = website_post_line(ok=True, site_copy=raw, site_reason="passed")
    assert "\n" not in line
    assert "website display verification passed" in line
    fail = website_post_line(
        ok=False,
        site_copy="- Site opened: yes\n- BOT Chain name: no\n- Result: failed",
        site_reason="no_botchain_name",
    )
    assert "\n" not in fail
    assert "BOT Chain name not found" in fail


def test_early_final_ignores_pre_september_name_duplicate():
    from datetime import datetime, timezone

    from bot.workflow_kpi_result_push import pick_early_final_progress_row

    july = datetime(2026, 7, 17, tzinfo=timezone.utc)
    sept = datetime(2026, 9, 4, tzinfo=timezone.utc)
    rows = [
        {
            "record_id": "rec-old",
            "fields": {
                "项目名称 Project Name": "Warden",
                "主网上线时间": july.isoformat(),
                "KPI 统筹": "",
            },
        },
        {
            "record_id": "rec-held",
            "fields": {
                "项目名称 Project Name": "Warden",
                "主网上线时间": sept.isoformat(),
                "KPI 统筹": "暂扣整改",
            },
        },
    ]
    hit = pick_early_final_progress_row(
        rows,
        project_name="Warden",
        name_field="项目名称 Project Name",
    )
    assert hit is not None
    assert hit["record_id"] == "rec-held"


def test_final_post_fills_first_check_from_live_plus_7():
    text = format_result_post(
        project="Coupon System",
        bd_name="Ramesh",
        bd_open_id="",
        live_date="2026-09-09",
        check_date="2026-10-08",
        twitter_ok=True,
        twitter_line="`6` original posts. Meets the Twitter requirement.",
        pr_ok=True,
        pr_line="https://x.com/couponsystem/status/1",
        website_ok=True,
        website_line="website display verification passed",
        onchain_ok=True,
        onchain_line="`12` wallets, `22` txs. Meets the wallet and on-chain requirement.",
        fixes=[],
        final=True,
        final_trigger="submit",
        first_check_date="",
    )
    assert "**First check:** `2026-09-16` · Held for rectification" in text
    assert "**Second check:** `2026-10-08` · final (triggered by submit)" in text
    assert "**Result:** Valid KPI" in text


def test_pending_rows_skip_posted_and_non_september():
    live = datetime(2026, 9, 14, tzinfo=timezone.utc)
    october = datetime(2026, 10, 1, tzinfo=timezone.utc)
    records = [
        {
            "record_id": "rec28ah3MsNpTG",
            "fields": {
                "项目名称 Project Name": "Intentswapbot",
                "项目状态": "主网上线",
                "主网上线时间": live.isoformat(),
            },
        },
        {
            "record_id": "rec-new",
            "fields": {
                "项目名称 Project Name": "Newproj",
                "项目状态": "主网上线",
                "主网上线时间": live.isoformat(),
            },
        },
        {
            "record_id": "rec-oct",
            "fields": {
                "项目名称 Project Name": "October",
                "项目状态": "主网上线",
                "主网上线时间": october.isoformat(),
            },
        },
    ]
    rows = pending_september_rows(
        records,
        skip_ids={"rec28ah3MsNpTG", "rec28abJciwa4a"},
    )
    assert [row["record_id"] for row in rows] == ["rec-new"]
    assert is_september_2026_live(records[1]["fields"])
    assert not is_september_2026_live(records[2]["fields"])


def test_stored_pass_copy_keeps_the_numbers():
    twitter = (
        "Twitter operations verification: official account @demo posted 7 "
        "original posts in the last 30 days (threshold ≥5); "
        "Twitter operations verification passed"
    )
    chain = (
        "User and interaction verification: 6 unique wallets, "
        "7 successful core txs (threshold ≥3 wallets and ≥5 txs); "
        "user and interaction verification passed"
    )
    assert twitter_line_from_copy(twitter).startswith("`7` original posts.")
    assert onchain_line_from_copy(chain).startswith("`6` wallets, `7` txs.")


def test_audit_skips_passed_items_and_writes_held_coord(monkeypatch):
    called = {"twitter": 0, "website": 0, "onchain": 0, "held": 0, "pass_chain": 0}

    def boom_twitter(*_a, **_k):
        called["twitter"] += 1
        raise AssertionError("passed twitter must not be rechecked")

    def boom_website(*_a, **_k):
        called["website"] += 1
        raise AssertionError("passed website must not be rechecked")

    def onchain(*_a, **_k):
        called["onchain"] += 1
        return {
            "contract": "",
            "wallets": 0,
            "txs": 0,
            "reason": "no_contract",
            "copy": "",
            "passed": False,
        }

    monkeypatch.setattr("bot.workflow_kpi1_twitter.audit_kpi1_for_fields", boom_twitter)
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter.fill_kpi2_pr_from_twitter",
        lambda *a, **k: "https://x.com/demo/status/9",
    )
    monkeypatch.setattr("bot.workflow_kpi3_website.audit_kpi3_for_fields", boom_website)
    monkeypatch.setattr("bot.workflow_kpi6_onchain.audit_kpi6_for_fields", onchain)
    monkeypatch.setattr(
        "bot.workflow_kpi45_live.fill_kpi45_for_fields",
        lambda *a, **k: "already_filled",
    )
    monkeypatch.setattr(
        "bot.workflow_kpi_pass_chain.write_kpi2_result",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "bot.workflow_kpi_pass_chain.apply_pass_chain",
        lambda *a, **k: called.__setitem__("pass_chain", called["pass_chain"] + 1),
    )

    def held(*_a, **_k):
        called["held"] += 1

    monkeypatch.setattr("bot.workflow_kpi_result_push.write_held_coord", held)

    class Cfg:
        workflow_base_app_token = "app"
        workflow_progress_table_id = "tbl"
        workflow_live_onboard_bd_field = "BD"

    fields = {
        "推特验证结果": "通过",
        "KPI 1 - Twitter运营验证": "posted 7 original posts",
        "官网验证结果": "通过",
        "KPI 3 - 官网展示验证": "Website display verification passed",
        "产品可用验证结果": "通过",
        "独立性验证结果": "通过",
        "交互验证结果": "不通过",
        "主网上线时间": "2026-09-14",
        "BD": [{"id": "ou_bd", "name": "Ada"}],
    }
    built = audit_first_check("tok", Cfg(), "rec1", fields, project_name="Swing")
    assert called == {"twitter": 0, "website": 0, "onchain": 1, "held": 1, "pass_chain": 0}
    assert built["valid"] is False
    assert "Held for rectification" in built["markdown"]
    assert "`7` original posts." in built["markdown"]
    assert "KPI 7" not in built["markdown"]
