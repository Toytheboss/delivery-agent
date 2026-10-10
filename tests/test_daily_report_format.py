"""Daily report eight-section format."""

from __future__ import annotations

from bot.metrics import (
    _classify_kpi_write,
    _fmt_kind_line,
    format_daily_report_zh,
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


def test_fmt_kind_line_caps_name_list() -> None:
    lines: list[str] = []
    names = [f"Proj{i}" for i in range(30)]
    _fmt_kind_line(lines, label="新群归档", count=30, names=names, name_limit=5)
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
            "folder_new_groups_today": 2,
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
                "today_mainnet_live": 1,
                "today_mainnet_live_names": ["Alpha"],
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
                    "folder_chat_added": 2,
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
                    "folder_chat_added": ["Nexa", "Mandate"],
                    "mark_live": ["Nexa"],
                    "verify_alert": ["Nexa", "Botter"],
                    "kpi_early_final": ["Spinner"],
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
    assert "新群归档：2" in text
    assert "补交终审" in text
    assert "Verify 告警：2" in text
    assert "字段写入：3" in text
