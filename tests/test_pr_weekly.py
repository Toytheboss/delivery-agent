from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from bot.workflow_pr_weekly import (
    TZ,
    build_pr_weekly_ping,
    collect_week_prs,
    in_daily_window,
    in_ping_window,
    period_label,
    period_short,
    report_window,
    week_window,
)


def test_week_window_on_wednesday():
    now = datetime(2026, 9, 23, 13, 50, tzinfo=TZ)
    start, end = week_window(now)
    assert start == datetime(2026, 9, 20, tzinfo=TZ)
    assert end == datetime(2026, 9, 27, tzinfo=TZ)
    assert period_label(start, end) == "2026-09-20 ~ 2026-09-27"
    assert period_short(start, end) == "9/20–9/27"


def test_week_window_at_sunday_midnight():
    now = datetime(2026, 9, 27, 0, 0, tzinfo=TZ)
    start, end = week_window(now)
    assert start == datetime(2026, 9, 20, tzinfo=TZ)
    assert end == datetime(2026, 9, 27, tzinfo=TZ)


def test_monday_ping_collects_sunday_daytime_same_period():
    now = datetime(2026, 9, 28, 0, 0, tzinfo=TZ)
    start, collect_end, label_end = report_window(now, ping=True)
    assert start == datetime(2026, 9, 20, tzinfo=TZ)
    assert collect_end == now
    assert label_end == datetime(2026, 9, 27, tzinfo=TZ)
    assert period_label(start, label_end) == "2026-09-20 ~ 2026-09-27"


def test_wednesday_report_window_is_in_progress_week():
    now = datetime(2026, 9, 23, 0, 0, tzinfo=TZ)
    start, collect_end, label_end = report_window(now, ping=False)
    assert start == datetime(2026, 9, 20, tzinfo=TZ)
    assert collect_end == datetime(2026, 9, 27, tzinfo=TZ)
    assert label_end == collect_end


def test_ping_window_is_monday_midnight_by_default():
    cfg = SimpleNamespace(pr_weekly_weekday=0, pr_weekly_hour=0)
    assert in_ping_window(cfg, datetime(2026, 9, 28, 0, 10, tzinfo=TZ)) is True
    assert in_ping_window(cfg, datetime(2026, 9, 27, 0, 10, tzinfo=TZ)) is False
    assert in_daily_window(cfg, datetime(2026, 9, 24, 0, 10, tzinfo=TZ)) is True


def test_ping_mentions_lighter_jasper_and_copy():
    start = datetime(2026, 9, 20, tzinfo=TZ)
    end = datetime(2026, 9, 27, tzinfo=TZ)
    text = build_pr_weekly_ping(
        start=start,
        end=end,
        count=5,
        assignees=[
            {"name": "Lighter", "open_id": "ou_lighter"},
            {"name": "Jasper", "open_id": "ou_jasper"},
        ],
        table_url_value="https://example.com/pr-table",
    )
    assert text.startswith(
        '<at user_id="ou_lighter">Lighter</at> <at user_id="ou_jasper">Jasper</at>'
    )
    assert "9/20–9/27" in text
    assert "Botchain 生态项目方推特转发需求已汇总" in text
    assert "社媒和社群支持" in text
    assert "https://example.com/pr-table" in text


def test_collect_prefers_event_over_record_mtime():
    start = datetime(2026, 9, 20, tzinfo=TZ)
    end = datetime(2026, 9, 27, tzinfo=TZ)
    in_ms = int(datetime(2026, 9, 22, 12, 0, tzinfo=TZ).timestamp() * 1000)
    out_ms = int(datetime(2026, 9, 19, 12, 0, tzinfo=TZ).timestamp() * 1000)
    records = [
        {
            "record_id": "rec1",
            "last_modified_time": in_ms,
            "fields": {
                "项目名称 Project Name": "PromptMint",
                "已上线链接🔗": {"link": "https://prompt.example/"},
                "KPI 2 - PR 新闻链接验证": "https://x.com/a/status/1",
            },
        },
        {
            "record_id": "rec2",
            "last_modified_time": out_ms,
            "fields": {
                "项目名称 Project Name": "Old",
                "已上线链接🔗": "https://old.example/",
                "KPI 2 - PR 新闻链接验证": "https://x.com/old/status/1",
            },
        },
        {
            "record_id": "rec3",
            "last_modified_time": in_ms,
            "fields": {
                "项目名称 Project Name": "NoPR",
                "已上线链接🔗": "https://nopr.example/",
            },
        },
    ]
    events = [
        {
            "ts": "2026-09-22T10:00:00+08:00",
            "record_id": "rec1",
            "project": "PromptMint",
            "url": "https://x.com/a/status/99",
            "site": "https://prompt.example/",
        }
    ]
    rows = collect_week_prs(
        records,
        events,
        start=start,
        end=end,
        name_field="项目名称 Project Name",
        live_link_field="已上线链接🔗",
        pr_field="KPI 2 - PR 新闻链接验证",
    )
    assert [r["name"] for r in rows] == ["PromptMint"]
    assert rows[0]["url"] == "https://x.com/a/status/99"


def test_collect_falls_back_to_record_mtime():
    start = datetime(2026, 9, 20, tzinfo=TZ)
    end = datetime(2026, 9, 27, tzinfo=TZ)
    in_ms = int(datetime(2026, 9, 23, 8, 0, tzinfo=TZ).timestamp() * 1000)
    records = [
        {
            "record_id": "rec9",
            "last_modified_time": in_ms,
            "fields": {
                "项目名称 Project Name": "TaskForge",
                "已上线链接🔗": "https://task.example/",
                "KPI 2 - PR 新闻链接验证": "https://x.com/t/status/2",
            },
        }
    ]
    rows = collect_week_prs(
        records,
        [],
        start=start,
        end=end,
        name_field="项目名称 Project Name",
        live_link_field="已上线链接🔗",
        pr_field="KPI 2 - PR 新闻链接验证",
    )
    assert rows == [
        {
            "record_id": "rec9",
            "name": "TaskForge",
            "url": "https://x.com/t/status/2",
            "site": "https://task.example/",
        }
    ]


def test_disabled_skips():
    from bot.workflow_pr_weekly import run_pr_weekly_once

    cfg = SimpleNamespace(pr_weekly_enabled=False)
    result = run_pr_weekly_once(cfg)
    assert result["skipped"] is True
    assert result["reason"] == "disabled"


def test_run_once_daily_updates_without_ping(tmp_path):
    from bot.workflow_pr_weekly import run_pr_weekly_once

    cfg = SimpleNamespace(
        pr_weekly_enabled=True,
        pr_weekly_weekday=0,
        pr_weekly_hour=0,
        pr_weekly_state_file=str(tmp_path / "state.json"),
        pr_weekly_chat_id="oc_chat",
        pr_weekly_table_url="https://example.com/pr",
        pr_weekly_assignees=[],
        workflow_base_app_token="app",
        workflow_progress_table_id="tbl",
        workflow_project_name_field="项目名称 Project Name",
        workflow_live_link_field="已上线链接🔗",
        pr_capture_link_field="KPI 2 - PR 新闻链接验证",
        pr_capture_events_file=str(tmp_path / "events.jsonl"),
    )
    in_ms = int(datetime(2026, 9, 22, 12, 0, tzinfo=TZ).timestamp() * 1000)
    progress = [
        {
            "record_id": "rec1",
            "last_modified_time": in_ms,
            "fields": {
                "项目名称 Project Name": "PromptMint",
                "已上线链接🔗": "https://prompt.example/",
                "KPI 2 - PR 新闻链接验证": "https://x.com/a/status/1",
            },
        }
    ]
    with (
        patch.dict("os.environ", {"LARK_APP_ID": "id", "LARK_APP_SECRET": "secret"}),
        patch("bot.workflow_pr_weekly.get_tenant_access_token", return_value="tok"),
        patch("bot.workflow_pr_weekly.list_records", return_value=progress),
        patch("bot.workflow_pr_weekly.upsert_week_rows") as upsert,
        patch("bot.workflow_pr_weekly.send_text_to_chat") as send,
    ):
        wed = datetime(2026, 9, 23, 0, 10, tzinfo=TZ)
        result = run_pr_weekly_once(cfg, now=wed)
        assert result["updated"] is True
        assert result["sent"] is False
        assert result["reason"] == "daily_update"
        upsert.assert_called_once()
        send.assert_not_called()

        mon = datetime(2026, 9, 28, 0, 10, tzinfo=TZ)
        ping = run_pr_weekly_once(cfg, now=mon)
        assert ping["sent"] is True
        send.assert_called_once()
