"""Which chats get rotated out when the account's folders are full."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bot.folder_auto_add import select_rotate_chat_ids

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def _days_ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


def test_selects_oldest_quiet_chats_and_skips_recent() -> None:
    chosen = select_rotate_chat_ids(
        [(1, _days_ago(60)), (2, _days_ago(10)), (3, _days_ago(50))],
        pinned_ids=set(),
        peer_ids=None,
        now=NOW,
        inactive_days=45,
        limit=5,
    )
    assert chosen == [1, 3]


def test_never_seen_sorts_before_old() -> None:
    chosen = select_rotate_chat_ids(
        [(1, _days_ago(80)), (2, None)],
        pinned_ids=set(),
        peer_ids=None,
        now=NOW,
        inactive_days=45,
        limit=5,
    )
    assert chosen == [2, 1]


def test_skips_pinned_and_chats_the_other_bot_does_not_keep() -> None:
    chosen = select_rotate_chat_ids(
        [(1, None), (2, None), (3, None)],
        pinned_ids={1},
        peer_ids={1, 3},
        now=NOW,
        inactive_days=45,
        limit=5,
    )
    assert chosen == [3]


def test_limit_caps_the_batch() -> None:
    chosen = select_rotate_chat_ids(
        [(i, None) for i in range(10)],
        pinned_ids=set(),
        peer_ids=None,
        now=NOW,
        inactive_days=45,
        limit=3,
    )
    assert chosen == [0, 1, 2]
