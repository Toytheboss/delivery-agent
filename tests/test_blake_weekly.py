from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from bot.workflow_blake_weekly import (
    TZ,
    build_blake_ping,
    collect_week_projects,
    in_daily_window,
    in_ping_window,
    looks_chinese,
    period_label,
    period_short,
    report_monday,
    week_monday,
)


def test_week_bounds_on_wednesday():
    now = datetime(2026, 9, 23, 13, 50, tzinfo=TZ)
    monday = week_monday(now)
    assert monday == datetime(2026, 9, 21, tzinfo=TZ)
    assert period_label(monday) == "2026-09-21 ~ 2026-09-27"
    assert period_short(monday) == "9/21–9/27"


def test_week_bounds_at_sunday_midnight():
    now = datetime(2026, 9, 27, 0, 0, tzinfo=TZ)
    monday = week_monday(now)
    assert monday == datetime(2026, 9, 21, tzinfo=TZ)
    assert period_label(monday) == "2026-09-21 ~ 2026-09-27"


def test_report_monday_on_monday_ping_includes_sunday():
    now = datetime(2026, 9, 28, 0, 0, tzinfo=TZ)
    monday = report_monday(now, ping=True)
    assert monday == datetime(2026, 9, 21, tzinfo=TZ)
    assert period_label(monday) == "2026-09-21 ~ 2026-09-27"


def test_report_monday_on_wednesday_stays_current_week():
    now = datetime(2026, 9, 23, 0, 0, tzinfo=TZ)
    monday = report_monday(now, ping=False)
    assert monday == datetime(2026, 9, 21, tzinfo=TZ)


def test_ping_window_is_monday_midnight_by_default():
    cfg = SimpleNamespace(workflow_blake_weekly_weekday=0, workflow_blake_weekly_hour=0)
    assert in_ping_window(cfg, datetime(2026, 9, 28, 0, 15, tzinfo=TZ)) is True
    assert in_ping_window(cfg, datetime(2026, 9, 27, 0, 15, tzinfo=TZ)) is False
    assert in_daily_window(cfg, datetime(2026, 9, 23, 0, 15, tzinfo=TZ)) is True
    assert in_daily_window(cfg, datetime(2026, 9, 23, 1, 0, tzinfo=TZ)) is False


def test_looks_chinese():
    assert looks_chinese("半山精读版是传记阅读产品")
    assert not looks_chinese("Neon Arcade is a cyberpunk arcade")


def test_build_ping_mentions_blake_and_count():
    monday = datetime(2026, 9, 21, tzinfo=TZ)
    text = build_blake_ping(
        count=8,
        monday=monday,
        at_open_id="ou_blake",
        at_name="Blake-APP-Android (布莱克)",
        table_url_value="https://example.com/table",
    )
    assert '<at user_id="ou_blake">Blake-APP-Android (布莱克)</at>' in text
    assert "一共 8 个" in text
    assert "9/21–9/27" in text
    assert "Botchain 主网上线" in text
    assert "https://example.com/table" in text


def test_collect_filters_status_and_live_week():
    monday = datetime(2026, 9, 21, tzinfo=TZ)
    live_ms = int(datetime(2026, 9, 22, 12, 0, tzinfo=TZ).timestamp() * 1000)
    outside_ms = int(datetime(2026, 9, 20, 12, 0, tzinfo=TZ).timestamp() * 1000)
    records = [
        {
            "record_id": "rec1",
            "fields": {
                "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                "项目名称 Project Name": "Neon Arcade",
                "主网上线时间": live_ms,
                "已上线链接🔗": {"link": "https://neon.example/", "text": "https://neon.example/"},
                "项目简介（1-2句话）": "A cyberpunk arcade",
            },
        },
        {
            "record_id": "rec2",
            "fields": {
                "项目状态": "主网部署中",
                "项目名称 Project Name": "Not Live",
                "主网上线时间": live_ms,
            },
        },
        {
            "record_id": "rec3",
            "fields": {
                "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                "项目名称 Project Name": "Last Week",
                "主网上线时间": outside_ms,
            },
        },
    ]
    rows = collect_week_projects(
        records,
        monday=monday,
        status_field="项目状态",
        name_field="项目名称 Project Name",
        live_link_field="已上线链接🔗",
        logo_field="项目logo（文件）",
    )
    assert [r["name"] for r in rows] == ["Neon Arcade"]
    assert rows[0]["site"] == "https://neon.example/"
    assert rows[0]["intro_source"] == "A cyberpunk arcade"


def test_collect_includes_sunday_afternoon_in_iso_week():
    monday = datetime(2026, 9, 21, tzinfo=TZ)
    sunday_ms = int(datetime(2026, 9, 27, 15, 30, tzinfo=TZ).timestamp() * 1000)
    records = [
        {
            "record_id": "rec-sun",
            "fields": {
                "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                "项目名称 Project Name": "Sunday Live",
                "主网上线时间": sunday_ms,
            },
        }
    ]
    rows = collect_week_projects(
        records,
        monday=monday,
        status_field="项目状态",
        name_field="项目名称 Project Name",
        live_link_field="已上线链接🔗",
        logo_field="项目logo（文件）",
    )
    assert [r["name"] for r in rows] == ["Sunday Live"]


def test_run_once_daily_updates_without_ping(tmp_path):
    from unittest.mock import patch

    from bot.workflow_blake_weekly import run_blake_weekly_once

    cfg = SimpleNamespace(
        workflow_blake_weekly_enabled=True,
        workflow_blake_weekly_weekday=0,
        workflow_blake_weekly_hour=0,
        workflow_blake_weekly_state_file=str(tmp_path / "state.json"),
        workflow_blake_weekly_chat_id="oc_chat",
        workflow_blake_weekly_at_open_id="",
        workflow_blake_weekly_at_name="Blake",
        workflow_blake_weekly_table_url="",
        workflow_base_app_token="app",
        workflow_progress_table_id="tbl",
        workflow_wallet_table_id="",
        workflow_status_field="项目状态",
        workflow_project_name_field="项目名称 Project Name",
        workflow_live_link_field="已上线链接🔗",
        workflow_logo_field="项目logo（文件）",
    )
    live_ms = int(datetime(2026, 9, 22, 12, 0, tzinfo=TZ).timestamp() * 1000)
    progress = [
        {
            "record_id": "rec1",
            "fields": {
                "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                "项目名称 Project Name": "Neon Arcade",
                "主网上线时间": live_ms,
                "已上线链接🔗": "https://neon.example/",
            },
        }
    ]
    with (
        patch.dict("os.environ", {"LARK_APP_ID": "id", "LARK_APP_SECRET": "secret"}),
        patch("bot.workflow_blake_weekly.get_tenant_access_token", return_value="tok"),
        patch("bot.workflow_blake_weekly.list_records", return_value=progress),
        patch("bot.workflow_blake_weekly.upsert_week_rows") as upsert,
        patch("bot.workflow_blake_weekly.send_text_to_chat") as send,
    ):
        wed = datetime(2026, 9, 23, 0, 10, tzinfo=TZ)
        result = run_blake_weekly_once(cfg, now=wed)
        assert result["updated"] is True
        assert result["sent"] is False
        assert result["reason"] == "daily_update"
        upsert.assert_called_once()
        send.assert_not_called()

        mon = datetime(2026, 9, 28, 0, 10, tzinfo=TZ)
        ping = run_blake_weekly_once(cfg, now=mon)
        assert ping["sent"] is True
        send.assert_called_once()
