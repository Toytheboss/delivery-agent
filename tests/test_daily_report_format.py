"""Daily report eight-section format."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from types import SimpleNamespace

from bot.metrics import (
    _classify_kpi_write,
    _fmt_kind_line,
    _form_first_send_names,
    _kpi_era_review_counts,
    _live_without_form,
    _progress_table_daily_counts,
    _summarize_delivery_funnel,
    format_business_data_zh,
    format_daily_report_zh,
    format_report_zh,
    split_telegram_text,
)


def test_split_telegram_text_keeps_short_message() -> None:
    assert split_telegram_text("hello") == ["hello"]


def test_split_telegram_text_splits_long_lines() -> None:
    body = "\n".join(f"line-{i}-" + ("x" * 80) for i in range(80))
    chunks = split_telegram_text(body, limit=500)
    assert len(chunks) >= 2
    assert all(len(c) <= 500 for c in chunks)
    assert "\n".join(chunks) == body


def test_form_first_sends_include_every_path_in_window() -> None:
    tz = timezone(timedelta(hours=8))
    since = datetime(2026, 10, 12, tzinfo=tz)
    projects = {
        "a": {"project_name": "Parliament", "first_sent_at": since.timestamp() + 3600, "source": "form_speaker"},
        "b": {"project_name": "Clearance", "first_sent_at": since.timestamp() + 7200, "source": "live_status_watch"},
        "c": {"project_name": "Old", "first_sent_at": since.timestamp() - 10, "source": "form_dispatch"},
    }
    assert _form_first_send_names(projects, since=since) == ["Parliament", "Clearance"]
    missing = _live_without_form(
        {"today_mainnet_live_records": [
            {"record_id": "a", "name": "Parliament"},
            {"record_id": "z", "name": "Orbit"},
        ]},
        projects,
    )
    assert missing == ["Orbit"]


def test_fmt_kind_line_does_not_invent_unnamed_extra() -> None:
    lines: list[str] = []
    _fmt_kind_line(lines, label="表单新发", count=12, names=["A", "B", "C", "D"])
    assert lines == ["· 表单新发：12（A、B、C、D）"]


def test_fmt_kind_line_caps_name_list() -> None:
    lines: list[str] = []
    names = [f"Proj{i}" for i in range(30)]
    _fmt_kind_line(lines, label="新增合作群", count=30, names=names, name_limit=5)
    assert lines and "等另 25 个" in lines[0]
    assert lines[0].count("Proj") == 5


def test_classify_kpi_write() -> None:
    assert _classify_kpi_write("进度表写入 KPI 3 官网：通过") == ("KPI3", "pass")
    assert _classify_kpi_write("进度表写入 KPI 6 链上交互：不通过") == ("KPI6", "fail")
    assert _classify_kpi_write("进度表写入 KPI 1 Twitter：通过") == ("KPI1", "pass")


def test_format_daily_report_has_eight_sections() -> None:
    text = format_daily_report_zh(
        {
            "today": "2026-10-09",
            "window_label": "过去24小时",
            "window_since": "2026-10-08T23:00:00+08:00",
            "window_until": "2026-10-09T23:00:00+08:00",
            "updated_at": "2026-10-09T23:00:00+08:00",
            "event_counts": True,
            "new_coop_groups_today": 2,
            "logo_fill_today": 1,
            "messages_processed_24h": 10,
            "messages_sent_24h": 4,
            "bot_messages": {
                "processed": 10,
                "sent": 4,
                "faq_bubbles": 2,
                "social": 3,
                "welcome": 5,
                "welcome_sequences": 2,
                "form": 1,
                "form_fail": 0,
                "human_review": 1,
                "mark_live": 1,
                "wallet_digest_sent": 1,
                "wallet_digest_new": 3,
                "absorb_learn": 0,
            },
            "progress": {
                "mainnet_live": 12,
                "today_mainnet_live": 1,
                "today_mainnet_live_names": ["Alpha"],
                "mainnet_deploying": 8,
                "kpi_coord_pass": 5,
                "today_kpi_coord_pass": 1,
                "today_kpi_coord_pass_names": ["Alpha"],
            },
            "wallet": {
                "today_new_projects": 2,
                "today_new_address_fields": 4,
            },
            "deploy_changes": {
                "baselined": True,
                "total": 3,
                "entered_testnet_deploy": ["T1"],
                "entered_mainnet_deploy": ["M1", "M2"],
                "left_mainnet_live": [],
            },
            "workflow": {
                "by_kind": {
                    "welcome_sequence_sent": 6,
                    "mark_live": 1,
                    "logo_uploaded_lark": 1,
                    "verification_push_onboard": 1,
                    "form_sent": 1,
                    "form_chase_reminder": 2,
                    "project_info_submit": 2,
                    "pr_support_written": 1,
                    "kpi_result_written": 3,
                    "kpi_early_final": 1,
                    "verify_alert": 2,
                    "pr_weekly_row": 5,
                    "frontend_weekly_row": 3,
                },
                "names_by_kind": {
                    "welcome_sequence_sent": ["Nexa", "Mandate"],
                    "mark_live": ["Nexa"],
                    "verify_alert": ["Nexa", "Botter"],
                    "kpi_early_final": ["Spinner"],
                },
                "new_names_by_kind": {
                    "welcome_sequence_sent": ["Nexa", "Mandate"],
                },
                "kpi_writes": {
                    "KPI3": {"pass": 2, "fail": 0, "other": 0},
                    "KPI6": {"pass": 0, "fail": 1, "other": 0},
                },
                "early_final": ["Spinner · 补交触发终审：Valid KPI"],
            },
            "message_mix": {
                "faq_replied": 2,
                "social_replied": 3,
                "silent": 4,
                "ignored": 0,
                "outbound": 4,
                "human_review": 1,
                "silent_reasons": {"please verify": 2, "llm needs human": 1},
            },
        }
    )
    for header in (
        "一、群触达",
        "二、部署管道",
        "三、上线漏斗",
        "四、物料与钱包",
        "五、KPI 审计",
        "六、协作告警",
        "七、周表例行",
        "八、Agent / 稳定性",
    ):
        assert header in text
    assert "新增合作群：2" in text
    assert "Nexa" in text and "Mandate" in text
    assert "新群归档" not in text
    assert "补交终审" in text
    assert "Verify 告警：2" in text
    assert "字段写入：3" in text
    assert "表单新发：1" in text
    assert "主网上线：累计 12（今日新增 1：Alpha）" in text
    assert "主网部署中：当前 8（今日新进 2：M1、M2）" in text
    assert "KPI 统筹通过：累计 5（今日新增 1：Alpha）" in text
    assert "进度表主网上线（按主网上线时间）" not in text
    assert "新进主网部署中" not in text


def test_format_daily_report_counts_every_form_send() -> None:
    text = format_daily_report_zh(
        {
            "today": "2026-10-12",
            "window_label": "2026-10-12 全天",
            "bot_messages": {"form": 12},
            "form_first_send_names": ["ProofPass", "Parliament", "Engrow"],
            "live_without_form_names": ["Orbit", "Pikachu"],
            "workflow": {"by_kind": {"form_sent": 4}, "names_by_kind": {"form_sent": ["ProofPass"]}},
            "progress": {},
            "wallet": {},
            "deploy_changes": {"baselined": True, "total": 0},
            "message_mix": {},
        }
    )
    assert "表单新发：3（ProofPass、Parliament、Engrow）" in text
    assert "主网上线但没有表单记录：2（Orbit、Pikachu）" in text
    assert "另" not in text.split("表单新发")[1].split("\n", 1)[0]
    assert "上线项目信息表单发出" in text
    assert "初审项目：0" in text
    assert "终审项目：0" in text


def test_delivery_funnel_counts_form_first_and_final() -> None:
    tz = timezone(timedelta(hours=8))
    since = datetime(2026, 10, 14, 0, 0, tzinfo=tz)
    records = [
        {
            "record_id": "rec-pass",
            "fields": {
                "项目名称 Project Name": "Oracle",
                "KPI Final": "通过",
                "KPI 1 - Twitter": "First check 2026-10-14 10:00\npassed",
                "KPI 6 - On chain interaction": "First check 2026-10-14 10:00\npassed",
                "KPI 7 - Ongoing operation": "First check 2026-10-14 10:00\npassed",
            },
        },
        {
            "record_id": "rec-held",
            "fields": {
                "项目名称 Project Name": "Escrow",
                "KPI Final": "暂扣整改",
                "KPI 1 - Twitter": "First check 2026-10-14 10:00\nfailed",
                "KPI 6 - On chain interaction": "First check 2026-10-14 10:00\nfailed",
            },
        },
        {
            "record_id": "rec-leap",
            "fields": {
                "项目名称 Project Name": "Leap",
                "KPI Final": "通过",
                "KPI 1 - Twitter": (
                    "First check 2026-10-14 10:00\nfailed\n"
                    "Recheck 2026-10-14 11:30\npassed"
                ),
                "KPI 7 - Ongoing operation": "First check 2026-10-14 11:30\npassed",
            },
        },
        {
            "record_id": "rec-final-only",
            "fields": {
                "项目名称 Project Name": "Shinobi",
                "KPI Final": "通过",
                "KPI 1 - Twitter": "Recheck 2026-10-14 19:40\npassed",
                "KPI 7 - Ongoing operation": "First check 2026-10-14 19:40\npassed",
            },
        },
    ]
    out = _summarize_delivery_funnel(
        since=since,
        form_sent_names=["Pinky"],
        chase_projects={
            "r1": {
                "project_name": "Ribbon",
                "done": True,
                "completed_at": datetime(2026, 10, 14, 8, tzinfo=tz).timestamp(),
            },
            "r2": {
                "project_name": "Old",
                "done": True,
                "completed_at": datetime(2026, 10, 13, 8, tzinfo=tz).timestamp(),
            },
            "r3": {
                "project_name": "Cancel",
                "done": True,
                "cancelled": True,
                "completed_at": datetime(2026, 10, 14, 9, tzinfo=tz).timestamp(),
            },
        },
        records=records,
        records_error=None,
        schedule_first={
            "rec-pass": "2026-10-14",
            "rec-held": "2026-10-14",
            "rec-leap": "2026-10-14",
        },
        schedule_second={"rec-leap": "2026-10-14", "rec-final-only": "2026-10-14"},
        events=[
            {
                "ts": "2026-10-14T11:30:00+08:00",
                "kind": "kpi_early_final",
                "project_name": "Leap",
                "record_id": "rec-leap",
                "text": "补交触发终审：Valid KPI",
            }
        ],
        name_field="项目名称 Project Name",
    )
    assert out["form_sent"] == ["Pinky"]
    assert out["form_received"] == ["Ribbon"]
    assert out["first_pass"] == ["Oracle"]
    assert out["first_held"] == ["Escrow", "Leap"]
    assert out["final_pass"] == ["Leap", "Shinobi"]
    assert out["final_fail"] == []


def test_weekly_report_includes_funnel_counts() -> None:
    text = format_report_zh(
        {
            "today": "2026-10-15",
            "week_start": "2026-10-08",
            "week_end": "2026-10-15",
            "counters": {},
            "derived": {},
            "wallet_lark": {"error": "skip"},
            "outbound_messages": {},
            "delivery_funnels": {
                "7d": {
                    "form_sent": ["A", "B"],
                    "form_received": ["A"],
                    "first_pass": ["Oracle"],
                    "first_held": ["Escrow"],
                    "final_pass": ["Leap"],
                    "final_fail": ["InheritX"],
                },
                "24h": {
                    "form_sent": ["B"],
                    "form_received": [],
                    "first_pass": [],
                    "first_held": ["Escrow"],
                    "final_pass": [],
                    "final_fail": [],
                },
            },
        }
    )
    assert "三、表单与考核" in text
    assert "上线项目信息表单发出：过去7天 2，过去24小时 1" in text
    assert "上线项目信息表单收回：过去7天 1，过去24小时 0" in text
    assert "初审项目：过去7天 2（通过 1，失败 1），过去24小时 1（通过 0，失败 1）" in text
    assert "终审项目：过去7天 2（通过 1，失败 1），过去24小时 0（通过 0，失败 0）" in text


def test_progress_table_stock_and_today_counts() -> None:
    tz = timezone(timedelta(hours=8))
    since = datetime(2026, 10, 16, tzinfo=tz)
    today_ms = int(datetime(2026, 10, 16, 12, 0, tzinfo=tz).timestamp() * 1000)
    yesterday_ms = int(datetime(2026, 10, 15, 12, 0, tzinfo=tz).timestamp() * 1000)
    cfg = SimpleNamespace(
        workflow_status_field="项目状态",
        workflow_project_name_field="项目名称 Project Name",
        workflow_logo_field="项目logo（文件）",
        workflow_trigger_status="BOT主网上线 Live on BOT Chain Mainnet",
    )
    out = _progress_table_daily_counts(
        cfg,
        since=since,
        records=[
            {
                "record_id": "live-old",
                "fields": {
                    "项目名称 Project Name": "LiveOld",
                    "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                    "主网上线时间": yesterday_ms,
                },
            },
            {
                "record_id": "live-new",
                "fields": {
                    "项目名称 Project Name": "LiveNew",
                    "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                    "主网上线时间": today_ms,
                },
            },
            {
                "record_id": "deploying",
                "fields": {
                    "项目名称 Project Name": "Deploying",
                    "项目状态": "主网部署中 Deploying on BOT Chain Mainnet",
                },
            },
            {
                "record_id": "kpi-old",
                "fields": {
                    "项目名称 Project Name": "KpiOld",
                    "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                    "主网上线时间": yesterday_ms,
                    "KPI Final": "通过",
                    "written time": yesterday_ms,
                },
            },
            {
                "record_id": "kpi-new",
                "fields": {
                    "项目名称 Project Name": "KpiNew",
                    "项目状态": "BOT主网上线 Live on BOT Chain Mainnet",
                    "主网上线时间": yesterday_ms,
                    "KPI Final": ["有效 KPI"],
                    "written time": today_ms,
                },
            },
            {
                "record_id": "held",
                "fields": {
                    "项目名称 Project Name": "Held",
                    "KPI Final": "暂扣整改",
                    "written time": today_ms,
                },
            },
        ],
    )
    assert out["mainnet_live"] == 4
    assert out["today_mainnet_live"] == 1
    assert out["today_mainnet_live_names"] == ["LiveNew"]
    assert out["mainnet_deploying"] == 1
    assert out["kpi_coord_pass"] == 2
    assert out["today_kpi_coord_pass"] == 1
    assert out["today_kpi_coord_pass_names"] == ["KpiNew"]


def test_format_daily_report_calendar_day_note() -> None:
    text = format_daily_report_zh(
        {
            "calendar_day": True,
            "window_label": "今日",
            "window_since": "2026-10-15T00:00:00+08:00",
            "window_until": "2026-10-15T12:00:00+08:00",
            "bot_messages": {},
            "progress": {},
            "wallet": {},
            "deploy_changes": {"baselined": True, "total": 0},
            "workflow": {"by_kind": {}, "names_by_kind": {}},
            "message_mix": {},
        }
    )
    assert "统计窗口：今日" in text
    assert "当天 00:00 至生成时刻" in text
    assert "不是滚动 24 小时" in text


def test_format_business_data_zh_all_time_lines() -> None:
    text = format_business_data_zh(
        {
            "mainnet_live": 120,
            "kpi_pass": 80,
            "form_sent": 100,
            "form_received": 90,
            "first_pass": 20,
            "first_held": 30,
            "final_pass": 35,
            "final_fail": 5,
        }
    )
    assert text.splitlines() == [
        "1. 主网上线项目累计：120",
        "2. 审核通过项目累计：80",
        "3. 上线项目信息表单发出：100",
        "4. 上线项目信息表单收回：90",
        "5. 初审项目：50，通过 20，失败 30",
        "6. 终审项目：40，通过 35，失败 5",
    ]


def test_format_business_data_zh_error() -> None:
    assert format_business_data_zh({"error": "lark down"}).startswith(
        "业务数据查询失败"
    )


def test_kpi_era_reviews_start_sep30_and_due_first() -> None:
    today = datetime(2026, 10, 21).date()
    tz = timezone(timedelta(hours=8))

    def live(day: str) -> str:
        return datetime.fromisoformat(day).replace(tzinfo=tz).isoformat()

    records = [
        {
            "record_id": "old",
            "fields": {
                "项目状态": "主网上线",
                "主网上线时间": live("2026-09-29"),
                "KPI Final": "通过",
            },
        },
        {
            "record_id": "too-new",
            "fields": {
                "项目状态": "主网上线",
                "主网上线时间": live("2026-10-19"),
                "KPI Final": "",
            },
        },
        {
            "record_id": "first-pass",
            "fields": {
                "项目状态": "主网上线",
                "主网上线时间": live("2026-10-01"),
                "KPI Final": "通过",
                "KPI 1 - Twitter": "First check 2026-10-04 10:00\npassed",
            },
        },
        {
            "record_id": "held",
            "fields": {
                "项目状态": "主网上线",
                "主网上线时间": live("2026-10-01"),
                "KPI Final": "暂扣整改",
                "KPI 1 - Twitter": "First check 2026-10-04 10:00\nfailed",
            },
        },
        {
            "record_id": "final-pass",
            "fields": {
                "项目状态": "主网上线",
                "主网上线时间": live("2026-10-01"),
                "KPI Final": "通过",
                "KPI 1 - Twitter": (
                    "First check 2026-10-04 10:00\nfailed\n"
                    "Recheck 2026-10-18 10:00\npassed"
                ),
            },
        },
        {
            "record_id": "final-fail",
            "fields": {
                "项目状态": "主网上线",
                "主网上线时间": live("2026-10-01"),
                "KPI Final": "不通过",
                "KPI 1 - Twitter": (
                    "First check 2026-10-04 10:00\nfailed\n"
                    "Recheck 2026-10-18 10:00\nfailed"
                ),
            },
        },
        {
            "record_id": "event-pass",
            "fields": {
                "项目状态": "主网上线",
                "主网上线时间": live("2026-10-01"),
                "KPI Final": "暂扣整改",
            },
        },
    ]
    events = [
        {
            "kind": "kpi_review_posted",
            "record_id": "event-pass",
            "review_round": "first",
            "outcome": "pass",
            "text": "初审通过",
        }
    ]
    out = _kpi_era_review_counts(
        records, events, today=today, first_days=3
    )
    assert out["first_pass"] == 2  # first-pass + event-pass
    assert out["first_held"] == 3  # held + final-pass + final-fail
    assert out["final_pass"] == 1
    assert out["final_fail"] == 1
