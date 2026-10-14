from __future__ import annotations

from scripts.sync_kpi2_results import FAIL, PASS, plan_updates


def test_plan_updates_passes_previously_entered_pr_link():
    records = [
        {
            "record_id": "rec_link",
            "fields": {
                "项目名称 Project Name": "Existing PR",
                "KPI 2 - PR Announcement": "https://x.com/project/status/1",
                "PR results": ["不通过"],
            },
        }
    ]

    assert plan_updates(
        records,
        link_field="KPI 2 - PR Announcement",
        result_field="PR results",
    ) == [
        {
            "record_id": "rec_link",
            "project": "Existing PR",
            "link": "https://x.com/project/status/1",
            "current": FAIL,
            "wanted": PASS,
        }
    ]


def test_plan_updates_skips_empty_pr_links_by_default():
    records = [
        {
            "record_id": "rec_empty",
            "fields": {
                "Project name": "No PR",
                "KPI 2 - PR Announcement": "",
                "PR results": [PASS],
            },
        },
        {
            "record_id": "rec_current",
            "fields": {
                "Project name": "Already correct",
                "KPI 2 - PR Announcement": "https://example.com/press",
                "PR results": [PASS],
            },
        },
    ]

    assert plan_updates(
        records,
        link_field="KPI 2 - PR Announcement",
        result_field="PR results",
    ) == []

    assert plan_updates(
        records,
        link_field="KPI 2 - PR Announcement",
        result_field="PR results",
        include_empty=True,
    ) == [
        {
            "record_id": "rec_empty",
            "project": "No PR",
            "link": "",
            "current": PASS,
            "wanted": FAIL,
        }
    ]
