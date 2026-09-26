from __future__ import annotations

from scripts.sync_kpi2_results import FAIL, PASS, plan_updates


def test_plan_updates_passes_previously_entered_pr_link():
    records = [
        {
            "record_id": "rec_link",
            "fields": {
                "项目名称 Project Name": "Existing PR",
                "KPI 2 - PR 新闻链接验证": "https://x.com/project/status/1",
                "新闻验证结果": ["不通过"],
            },
        }
    ]

    assert plan_updates(
        records,
        link_field="KPI 2 - PR 新闻链接验证",
        result_field="新闻验证结果",
    ) == [
        {
            "record_id": "rec_link",
            "project": "Existing PR",
            "link": "https://x.com/project/status/1",
            "current": FAIL,
            "wanted": PASS,
        }
    ]


def test_plan_updates_fails_empty_pr_link_and_skips_correct_rows():
    records = [
        {
            "record_id": "rec_empty",
            "fields": {
                "Project name": "No PR",
                "KPI 2 - PR 新闻链接验证": "",
                "新闻验证结果": [PASS],
            },
        },
        {
            "record_id": "rec_current",
            "fields": {
                "Project name": "Already correct",
                "KPI 2 - PR 新闻链接验证": "https://example.com/press",
                "新闻验证结果": [PASS],
            },
        },
    ]

    assert plan_updates(
        records,
        link_field="KPI 2 - PR 新闻链接验证",
        result_field="新闻验证结果",
    ) == [
        {
            "record_id": "rec_empty",
            "project": "No PR",
            "link": "",
            "current": PASS,
            "wanted": FAIL,
        }
    ]
