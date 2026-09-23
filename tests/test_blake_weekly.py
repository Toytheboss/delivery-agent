from __future__ import annotations

from datetime import datetime

from bot.workflow_blake_weekly import (
    TZ,
    build_blake_ping,
    collect_week_projects,
    looks_chinese,
    period_label,
    period_short,
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
