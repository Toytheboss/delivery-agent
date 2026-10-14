"""Telegram daily report and console share one period-report ledger."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from bot import dashboard_snapshot, metrics


def _event(ts: datetime, kind: str, **extra: object) -> str:
    return json.dumps({"ts": ts.isoformat(timespec="seconds"), "kind": kind, **extra})


def test_window_count_uses_hour_buckets_when_they_cover_the_window() -> None:
    now = metrics._now()
    since = now - timedelta(hours=24)
    bucket = {
        "by_day": {now.strftime("%Y-%m-%d"): 50},
        "by_hour": {
            metrics._hour_key(now): 3,
            metrics._hour_key(now - timedelta(hours=5)): 4,
            metrics._hour_key(now - timedelta(hours=30)): 100,
        },
    }
    n, exact = metrics._window_count(
        bucket,
        since=since,
        day_days=[now.strftime("%Y-%m-%d")],
        hourly_since=now - timedelta(days=3),
    )
    assert (n, exact) == (7, True)


def test_window_count_falls_back_to_days_before_hourly_tracking() -> None:
    now = metrics._now()
    day = now.strftime("%Y-%m-%d")
    bucket = {"by_day": {day: 50}, "by_hour": {metrics._hour_key(now): 3}}
    n, exact = metrics._window_count(
        bucket,
        since=now - timedelta(hours=24),
        day_days=[day],
        hourly_since=now - timedelta(hours=2),
    )
    assert (n, exact) == (50, False)


def test_workflow_summary_dedupes_bots_and_counts_first_ever(tmp_path) -> None:
    now = metrics._now()
    old = now - timedelta(days=10)
    recent = now - timedelta(hours=2)
    rows = [
        _event(old, "folder_chat_added", chat_id=1, project_name="Old Group"),
        # Same group archived again by the other bot: not new.
        _event(recent, "folder_chat_added", chat_id=1, project_name="Old Group"),
        # New group archived by both bots: counted once.
        _event(recent, "folder_chat_added", chat_id=2, project_name="Fresh"),
        _event(recent, "folder_chat_added", chat_id=2, project_name="Fresh"),
        _event(recent, "logo_uploaded_lark", record_id="r1", project_name="Fresh"),
        _event(recent, "logo_uploaded_lark", record_id="r1", project_name="Fresh"),
        _event(recent, "welcome_sequence_sent", chat_id=2, project_name="Fresh"),
        _event(recent, "welcome_sequence_sent", chat_id=2, project_name="Fresh"),
    ]
    path = tmp_path / "workflow_events.jsonl"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    out = metrics._workflow_window_summary(
        SimpleNamespace(workflow_events_file=str(path)),
        since=now - timedelta(hours=24),
    )
    assert out["available"] is True
    assert out["by_kind"]["folder_chat_added"] == 3
    assert out["new_by_kind"]["folder_chat_added"] == 1
    assert out["new_names_by_kind"]["folder_chat_added"] == ["Fresh"]
    assert out["unique_by_kind"]["logo_uploaded_lark"] == 1
    assert out["new_by_kind"]["welcome_sequence_sent"] == 1
    assert out["by_kind"]["welcome_sequence_sent"] == 2


def test_folder_line_uses_first_ever_names() -> None:
    text = metrics.format_daily_report_zh(
        {
            "event_counts": True,
            "counter_precision": "hourly",
            "folder_new_groups_today": 1,
            "bot_messages": {},
            "workflow": {
                "by_kind": {"folder_chat_added": 3},
                "names_by_kind": {"folder_chat_added": ["Old Group", "Fresh"]},
                "new_names_by_kind": {"folder_chat_added": ["Fresh"]},
            },
            "progress": {},
            "wallet": {},
            "deploy_changes": {"baselined": True, "total": 0},
            "message_mix": {},
        }
    )
    assert "新群归档：1（Fresh）" in text
    assert "计数器按小时" in text


def test_published_reports_round_trip(tmp_path, monkeypatch) -> None:
    target = tmp_path / "period_reports.json"
    config = SimpleNamespace(
        metrics_period_reports_file=str(target),
        dashboard_period_reports_file=str(target),
    )
    monkeypatch.setattr(
        metrics,
        "build_period_reports",
        lambda _config: {"24h": {"metrics": {"folder_auto_add_success": 4}}},
    )
    assert metrics.publish_period_reports(config) == target
    loaded = dashboard_snapshot.load_published_period_reports(config)
    assert loaded is not None
    assert loaded["reports"]["24h"]["metrics"]["folder_auto_add_success"] == 4


def test_stale_published_reports_are_ignored(tmp_path) -> None:
    target = tmp_path / "period_reports.json"
    stale = metrics._now() - timedelta(hours=2)
    target.write_text(
        json.dumps({"generated_at": stale.isoformat(), "reports": {"24h": {}}}),
        encoding="utf-8",
    )
    config = SimpleNamespace(dashboard_period_reports_file=str(target))
    assert dashboard_snapshot.load_published_period_reports(config) is None


def test_unconfigured_host_does_not_publish() -> None:
    assert metrics.publish_period_reports(SimpleNamespace()) is None
