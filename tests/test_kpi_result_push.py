from datetime import datetime, timezone

from bot.workflow_kpi_result_push import (
    format_result_post,
    is_september_2026_live,
    onchain_post_line,
    pending_september_rows,
    pr_post_line,
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
    assert "KPI failed" not in text
    assert "KPI 7" not in text
    assert text.index("**Failed**") < text.index("**Passed**")
    assert "**KPI 2 PR:** Not submitted" in text
    assert "Fix within `2` weeks: share the Twitter PR link in the Telegram group." in text
    assert "The second review is final." in text
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
