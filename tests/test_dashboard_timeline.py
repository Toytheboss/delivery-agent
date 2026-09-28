from bot.dashboard_snapshot import _project_state_events, _timeline_events


def test_timeline_keeps_telegram_outbound_drops_faq_wrappers():
    rows = [
        {"kind": "telegram_outbound", "ts": "2026-09-28T10:00:00+08:00", "text": "Roy号在项目群发出：hi"},
        {"kind": "qa_silent", "ts": "2026-09-28T10:01:00+08:00", "text": "未回复"},
        {"kind": "qa_replied", "ts": "2026-09-28T10:02:00+08:00", "text": "回答了一次"},
        {"kind": "pr_support_written", "ts": "2026-09-28T10:03:00+08:00", "text": "PR"},
        {"kind": "form_sent", "ts": "", "text": "no ts"},
    ]
    out = _timeline_events(rows)
    kinds = [item["kind"] for item in out]
    assert kinds == ["pr_support_written", "telegram_outbound"]


def test_state_events_include_pr_kpi_onboard_and_chase():
    events = _project_state_events(
        record_id="rec1",
        name="Sample",
        fields={
            "KPI 2 - PR 新闻链接验证": "https://x.com/sample/status/1",
            "新闻验证结果": "通过",
            "推特验证结果": "通过",
            "KPI 判定时间": 1759000000000,
        },
        updated="2026-09-28T12:00:00+08:00",
        onboard_entry={"notify": "sent", "case": 1, "roy_checked_at": 1759000000},
        chase_meta={
            "first_sent_at": 1758900000,
            "last_sent_at": 1758910000,
            "reminders_sent": 2,
            "done": True,
            "completed_at": 1758920000,
        },
    )
    kinds = {item["kind"] for item in events}
    assert "verification_push_onboard" in kinds
    assert "pr_support_written" in kinds
    assert "kpi_result_written" in kinds
    assert "form_sent" in kinds
    assert "form_chase_reminder" in kinds
    assert "form_completed" in kinds
    assert any("case 1" in str(item.get("text") or "") for item in events)
    assert any("status/1" in str(item.get("text") or "") for item in events)
