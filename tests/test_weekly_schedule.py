from __future__ import annotations

from datetime import datetime

from bot.weekly_schedule import (
    TZ,
    ping_sent_recently,
    upcoming_send_at,
)


def test_sunday_night_skips_last_monday_and_waits_for_midnight():
    now = datetime(2026, 9, 27, 23, 49, tzinfo=TZ)
    slot = upcoming_send_at(now, weekday=0, hour=0, already_sent=False)
    assert slot == datetime(2026, 9, 28, 0, 0, tzinfo=TZ)


def test_monday_after_grace_does_not_catch_up():
    now = datetime(2026, 9, 28, 0, 10, tzinfo=TZ)
    slot = upcoming_send_at(now, weekday=0, hour=0, already_sent=False)
    assert slot == datetime(2026, 10, 5, 0, 0, tzinfo=TZ)


def test_already_sent_sunday_night_still_points_at_this_monday():
    now = datetime(2026, 9, 27, 23, 49, tzinfo=TZ)
    slot = upcoming_send_at(now, weekday=0, hour=0, already_sent=True)
    assert slot == datetime(2026, 9, 28, 0, 0, tzinfo=TZ)


def test_already_sent_at_monday_midnight_jumps_next_week():
    now = datetime(2026, 9, 28, 0, 0, tzinfo=TZ)
    slot = upcoming_send_at(now, weekday=0, hour=0, already_sent=True)
    assert slot == datetime(2026, 10, 5, 0, 0, tzinfo=TZ)


def test_ping_sent_recently_blocks_second_copy():
    now = datetime(2026, 9, 28, 0, 0, tzinfo=TZ)
    state = {"last_sent_at": "2026-09-27T23:49:00+08:00"}
    assert ping_sent_recently(state, now) is True
    later = datetime(2026, 9, 28, 18, 0, tzinfo=TZ)
    assert ping_sent_recently(state, later) is False
