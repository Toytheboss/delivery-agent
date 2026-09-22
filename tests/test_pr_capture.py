from __future__ import annotations

from types import SimpleNamespace

from bot.workflow_pr_capture import (
    build_pr_notify_text,
    collect_urls_from_message,
    is_pr_capture_command,
    is_tweet_url,
    pick_pr_url,
    tg_message_link,
)


def test_keyword_pr_support():
    assert is_pr_capture_command("pr support")
    assert is_pr_capture_command("PR Support")
    assert is_pr_capture_command("pr-support")
    assert is_pr_capture_command("/pr support")
    assert is_pr_capture_command("pr support!")
    assert not is_pr_capture_command("pr")
    assert not is_pr_capture_command("转发")
    assert not is_pr_capture_command("please pr support this")
    assert not is_pr_capture_command("tech support")


def test_pick_tweet_url_over_other_links():
    urls = [
        "https://botchain.ai",
        "https://x.com/foo/status/1234567890",
        "https://example.com/blog",
    ]
    assert pick_pr_url(urls) == "https://x.com/foo/status/1234567890"


def test_twitter_and_x_are_tweets():
    assert is_tweet_url("https://twitter.com/proj/status/99")
    assert is_tweet_url("https://www.x.com/proj/status/99?s=20")
    assert is_tweet_url("https://mobile.twitter.com/proj/status/99")
    assert not is_tweet_url("https://x.com/proj")
    assert not is_tweet_url("https://botchain.ai")


def test_fallback_to_first_http_url():
    assert pick_pr_url(["https://mirror.xyz/post/1"]) == "https://mirror.xyz/post/1"
    assert pick_pr_url([]) == ""


def test_collect_urls_from_text_and_entities():
    msg = SimpleNamespace(
        raw_text="Live: https://x.com/a/status/1 and more",
        entities=[SimpleNamespace(url="https://t.co/abc")],
        web_preview=SimpleNamespace(url="https://x.com/a/status/1"),
        media=SimpleNamespace(webpage=SimpleNamespace(url="https://x.com/a/status/1")),
    )
    urls = collect_urls_from_message(msg)
    assert "https://x.com/a/status/1" in urls
    assert "https://t.co/abc" in urls
    assert pick_pr_url(urls) == "https://x.com/a/status/1"


def test_tg_message_link_strips_minus_100():
    assert tg_message_link(-1001234567890, 42) == "https://t.me/c/1234567890/42"
    assert tg_message_link(-5404824061, 7) == "https://t.me/c/5404824061/7"


def test_notify_text_includes_project_and_url():
    text = build_pr_notify_text(
        project_name="TipJar",
        chat_title="TipJar <> Botchain",
        url="https://x.com/a/status/1",
        operator="@trent_one",
        record_id="recABC",
    )
    assert text.startswith("【KPI-PR 已收录】")
    assert "TipJar" in text
    assert "https://x.com/a/status/1" in text
    assert "@trent_one" in text
    assert "record=recABC" in text
