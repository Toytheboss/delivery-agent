from __future__ import annotations

import bot.casual_replies as casual
from bot.casual_replies import (
    begin_casual,
    casual_reply_kind,
    pick_casual_text,
    resolve_casual_kind,
)


def test_kind_matches_the_line():
    assert casual_reply_kind("Awesome") == "praise"
    assert casual_reply_kind("thanks") == "thanks"
    assert casual_reply_kind("thanks for sharing this") == "thanks"
    assert casual_reply_kind("收到") == "ack"
    assert casual_reply_kind("好的") == "ack"
    assert casual_reply_kind("gm") == "greeting"
    assert casual_reply_kind("https://x.com/foo/status/1") == "share"
    assert resolve_casual_kind("Yo Clem gm") == "greeting"
    assert resolve_casual_kind("are you sure??") is None
    assert casual_reply_kind("what is the chain id?") is None


def test_greeting_stays_in_the_same_time_of_day():
    for seed in range(60):
        morning = pick_casual_text("gm", seed=seed)
        assert casual._NIGHT_LINE_RE.search(morning) is None
        night = pick_casual_text("gn", seed=seed)
        assert casual._MORNING_LINE_RE.search(night) is None
        plain = pick_casual_text("hi", seed=seed)
        assert casual._MORNING_LINE_RE.search(plain) is None
        assert casual._NIGHT_LINE_RE.search(plain) is None


def test_recent_lines_are_not_repeated():
    recent: list[str] = []
    for seed in range(15):
        line = pick_casual_text("gm", seed=seed, recent=recent)
        assert line not in recent
        recent.append(line)
    assert len(set(recent)) == 15


def test_lexicon_drops_the_old_stock_lines():
    blobs = []
    for pool in casual._POOLS.values():
        blobs.extend(pool)
    joined = "\n".join(blobs).lower()
    assert "works for me" not in joined
    assert "thanks for sharing this" not in joined
    assert "thanks for letting me know" not in joined


def test_one_bot_per_window():
    import os
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CASUAL_REPLY_STATE"] = str(Path(tmp) / "casual.json")
        allowed, _ = begin_casual(42, 7, "qa_session")
        assert allowed
        same_message, _ = begin_casual(42, 7, "delivery_session")
        assert not same_message
        other_message, _ = begin_casual(42, 8, "delivery_session")
        assert not other_message
        same_bot, _ = begin_casual(42, 9, "qa_session")
        assert same_bot
