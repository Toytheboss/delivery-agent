from __future__ import annotations

from datetime import datetime, timezone

from bot.workflow_kpi1_twitter import (
    SH,
    _utc_stamp,
    _x_api,
    collect_originals,
    count_originals,
    find_mainnet_pr_url,
    is_mainnet_pr_tweet,
    original_status_links,
    tweet_has_project_name,
    x_api_configured,
)


def test_utc_stamp_is_actual_utc_not_shanghai_labeled_z():
    dt = datetime(2026, 9, 26, 8, 0, tzinfo=SH)
    assert _utc_stamp(dt) == "2026-09-26T00:00:00Z"


def test_x_api_configured_from_bearer(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_BEARER", raising=False)
    monkeypatch.delenv("X_API_KEY", raising=False)
    monkeypatch.delenv("X_API_SECRET", raising=False)
    monkeypatch.delenv("TWITTER_API_KEY", raising=False)
    monkeypatch.delenv("TWITTER_API_SECRET", raising=False)
    monkeypatch.delenv("TWITTER_API_KEY_SECRET", raising=False)
    assert x_api_configured() is False
    monkeypatch.setenv("X_BEARER_TOKEN", "aaa")
    assert x_api_configured() is True


def test_count_originals_uses_x_api_when_bearer_set(monkeypatch):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    tweets = [
        (datetime(2026, 9, 10, tzinfo=timezone.utc), "one", {}),
        (datetime(2026, 9, 11, tzinfo=timezone.utc), "two", {}),
        (datetime(2026, 9, 12, tzinfo=timezone.utc), "three", {}),
        (datetime(2026, 9, 13, tzinfo=timezone.utc), "four", {}),
        (datetime(2026, 9, 14, tzinfo=timezone.utc), "five", {}),
    ]
    monkeypatch.setenv("X_BEARER_TOKEN", "test")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_api", lambda handle, start: tweets)
    count, source = count_originals("demo", since=since)
    assert source == "x_api"
    assert count == 5


def test_count_originals_does_not_fall_back_when_x_api_fails(monkeypatch):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    monkeypatch.setenv("X_BEARER_TOKEN", "test")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_api", lambda handle, start: None)
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter._syndication",
        lambda handle: [(datetime(2026, 9, 10, tzinfo=timezone.utc), "cached", {})],
    )
    count, source = count_originals("demo", since=since)
    assert source == "unread"
    assert count is None


def test_x_api_paginates_and_keeps_posts_in_window(monkeypatch):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)

    class _Resp:
        def __init__(self, payload: dict) -> None:
            self.status_code = 200
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    def fake_get(path: str, bearer: str, params: dict | None = None):
        del bearer
        if path.startswith("/2/users/by/username/"):
            return _Resp({"data": {"id": "42"}})
        if (params or {}).get("pagination_token") == "n2":
            return _Resp(
                {
                    "data": [
                        {
                            "created_at": "2026-09-02T00:00:00.000Z",
                            "text": "second",
                        }
                    ],
                    "meta": {},
                }
            )
        return _Resp(
            {
                "data": [
                    {"created_at": "2026-09-20T00:00:00.000Z", "text": "first"},
                ],
                "meta": {"next_token": "n2"},
            }
        )

    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._BEARER_CACHE", "")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_get", fake_get)
    rows = _x_api("Demo", since)
    texts = [text for _dt, text, _extra in rows]
    assert texts == ["first", "second"]


def test_x_api_stops_paging_after_window(monkeypatch):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    calls: list[dict | None] = []

    class _Resp:
        def __init__(self, payload: dict) -> None:
            self.status_code = 200
            self._payload = payload

        def json(self) -> dict:
            return self._payload

    def fake_get(path: str, bearer: str, params: dict | None = None):
        del bearer
        if path.startswith("/2/users/by/username/"):
            return _Resp({"data": {"id": "42"}})
        calls.append(params)
        return _Resp(
            {
                "data": [
                    {"created_at": "2026-09-20T00:00:00.000Z", "text": "in"},
                    {"created_at": "2026-08-01T00:00:00.000Z", "text": "old"},
                ],
                "meta": {"next_token": "should-not-follow"},
            }
        )

    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_get", fake_get)
    rows = _x_api("Demo", since)
    assert [text for _dt, text, _extra in rows] == ["in"]
    tweet_calls = [p for p in calls if p is not None]
    assert len(tweet_calls) == 1
    assert "pagination_token" not in (tweet_calls[0] or {})


def test_original_status_links_newest_five_skip_retweets():
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [
        (datetime(2026, 9, 10, tzinfo=timezone.utc), "old", {"id": "10"}),
        (datetime(2026, 9, 20, tzinfo=timezone.utc), "RT @x hi", {"id": "20"}),
        (datetime(2026, 9, 21, tzinfo=timezone.utc), "a", {"id": "21"}),
        (datetime(2026, 9, 22, tzinfo=timezone.utc), "b", {"id_str": "22"}),
        (datetime(2026, 9, 23, tzinfo=timezone.utc), "c", {"id": "23"}),
        (datetime(2026, 9, 24, tzinfo=timezone.utc), "d", {"id": "24"}),
        (datetime(2026, 9, 25, tzinfo=timezone.utc), "e", {"id": "25"}),
        (datetime(2026, 8, 1, tzinfo=timezone.utc), "too old", {"id": "1"}),
    ]
    links = original_status_links("Demo", rows, since=since)
    assert links == [
        "https://x.com/Demo/status/25",
        "https://x.com/Demo/status/24",
        "https://x.com/Demo/status/23",
        "https://x.com/Demo/status/22",
        "https://x.com/Demo/status/21",
        "https://x.com/Demo/status/10",
    ]


def test_collect_originals_returns_links_from_x_api(monkeypatch):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    tweets = [
        (datetime(2026, 9, 14, tzinfo=timezone.utc), "five", {"id": "5"}),
        (datetime(2026, 9, 13, tzinfo=timezone.utc), "four", {"id": "4"}),
    ]
    monkeypatch.setenv("X_BEARER_TOKEN", "test")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_api", lambda handle, start: tweets)
    count, source, links = collect_originals("demo", since=since)
    assert source == "x_api"
    assert count == 2
    assert links == [
        "https://x.com/demo/status/5",
        "https://x.com/demo/status/4",
    ]


def test_mainnet_pr_needs_project_name_chain_and_live():
    extra = {"id": "9"}
    assert is_mainnet_pr_tweet(
        "BanshanBook is live on Botchain mainnet today",
        extra,
        project_name="BanshanBook",
    )
    assert is_mainnet_pr_tweet(
        "Banshan Book launched on BOT Chain",
        extra,
        project_name="BanshanBook",
    )
    assert not is_mainnet_pr_tweet(
        "We are live on Botchain mainnet today",
        extra,
        project_name="BanshanBook",
    )
    assert not is_mainnet_pr_tweet(
        "BanshanBook shipped a new feature",
        extra,
        project_name="BanshanBook",
    )
    assert not is_mainnet_pr_tweet(
        "RT @x BanshanBook is live on Botchain mainnet",
        extra,
        project_name="BanshanBook",
    )
    assert tweet_has_project_name("go live with Banshan Book now", "BanshanBook")


def test_find_mainnet_pr_url_takes_newest_hit():
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [
        (
            datetime(2026, 9, 10, tzinfo=timezone.utc),
            "BanshanBook is live on Botchain mainnet",
            {"id": "10"},
        ),
        (
            datetime(2026, 9, 20, tzinfo=timezone.utc),
            "BanshanBook now live on BOT Chain",
            {"id": "20"},
        ),
        (
            datetime(2026, 9, 22, tzinfo=timezone.utc),
            "unrelated gm",
            {"id": "22"},
        ),
    ]
    assert (
        find_mainnet_pr_url("banshanbook", rows, since=since, project_name="BanshanBook")
        == "https://x.com/banshanbook/status/20"
    )


def test_maybe_write_kpi2_skips_filled_cell(monkeypatch):
    from bot.workflow_kpi1_twitter import maybe_write_kpi2_from_tweets

    called: list[object] = []
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter.update_record",
        lambda *args, **kwargs: called.append(args),
    )

    class Cfg:
        pr_capture_link_field = "KPI 2 - PR 新闻链接验证"
        workflow_live_link_field = "已上线链接🔗"
        workflow_project_link_field = "项目链接"
        workflow_base_app_token = "app"
        workflow_progress_table_id = "tbl"

    rows = [
        (
            datetime(2026, 9, 20, tzinfo=timezone.utc),
            "BanshanBook is live on Botchain mainnet",
            {"id": "20"},
        )
    ]
    url = maybe_write_kpi2_from_tweets(
        "tok",
        Cfg(),
        "rec1",
        {"KPI 2 - PR 新闻链接验证": "https://x.com/keep/status/1"},
        project_name="BanshanBook",
        handle="banshanbook",
        rows=rows,
        since=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert url == ""
    assert called == []


def test_maybe_write_kpi2_fills_empty_cell(monkeypatch):
    from bot.workflow_kpi1_twitter import maybe_write_kpi2_from_tweets

    patches: list[dict] = []
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter.update_record",
        lambda token, app, table, rid, fields: patches.append(fields),
    )
    monkeypatch.setattr(
        "bot.workflow_pr_weekly.log_capture_event", lambda *a, **k: None
    )

    class Cfg:
        pr_capture_link_field = "KPI 2 - PR 新闻链接验证"
        workflow_live_link_field = "已上线链接🔗"
        workflow_project_link_field = "项目链接"
        workflow_base_app_token = "app"
        workflow_progress_table_id = "tbl"

    rows = [
        (
            datetime(2026, 9, 20, tzinfo=timezone.utc),
            "BanshanBook is live on Botchain mainnet",
            {"id": "20"},
        )
    ]
    url = maybe_write_kpi2_from_tweets(
        "tok",
        Cfg(),
        "rec1",
        {},
        project_name="BanshanBook",
        handle="banshanbook",
        rows=rows,
        since=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert url == "https://x.com/banshanbook/status/20"
    assert patches == [
        {
            "KPI 2 - PR 新闻链接验证": "https://x.com/banshanbook/status/20",
            "新闻验证结果": "通过",
        }
    ]
