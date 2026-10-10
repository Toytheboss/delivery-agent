from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.workflow_kpi1_twitter import (
    SH,
    _utc_stamp,
    _x_api,
    collect_originals,
    count_originals,
    evaluate_kpi1,
    find_mainnet_pr_url,
    is_mainnet_pr_tweet,
    original_status_links,
    tweet_has_project_name,
    x_api_configured,
)


@pytest.fixture(autouse=True)
def _user_id_cache(tmp_path, monkeypatch):
    path = tmp_path / "x_user_id_cache.json"
    monkeypatch.setattr("bot.workflow_kpi1_twitter._USER_ID_CACHE_PATH", path)
    return path


class _Resp:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _timeline_get(calls: list[str], *, bad_ids: frozenset[str] = frozenset()):
    def fake_get(path: str, bearer: str, params: dict | None = None):
        del bearer, params
        calls.append(path)
        if path.startswith("/2/users/by/username/"):
            return _Resp({"data": {"id": "42"}})
        user_id = path.split("/")[3]
        if user_id in bad_ids:
            return _Resp({"errors": [{"title": "Not Found Error"}]}, status_code=404)
        return _Resp(
            {"data": [{"created_at": "2026-09-20T00:00:00.000Z", "text": "in"}], "meta": {}}
        )

    return fake_get


def test_x_api_reuses_cached_user_id(monkeypatch, _user_id_cache):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    calls: list[str] = []
    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_get", _timeline_get(calls))
    assert [t for _d, t, _e in _x_api("Demo", since)] == ["in"]
    assert [t for _d, t, _e in _x_api("demo", since)] == ["in"]
    assert calls == [
        "/2/users/by/username/Demo",
        "/2/users/42/tweets",
        "/2/users/42/tweets",
    ]
    assert '"demo": "42"' in _user_id_cache.read_text(encoding="utf-8")


def test_x_api_looks_up_again_when_cached_id_fails(monkeypatch, _user_id_cache):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    _user_id_cache.write_text('{"demo": "7"}', encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter._x_get",
        _timeline_get(calls, bad_ids=frozenset({"7"})),
    )
    assert [t for _d, t, _e in _x_api("Demo", since)] == ["in"]
    assert calls == [
        "/2/users/7/tweets",
        "/2/users/by/username/Demo",
        "/2/users/42/tweets",
    ]
    assert '"demo": "42"' in _user_id_cache.read_text(encoding="utf-8")


def test_x_api_enough_reads_one_small_page(monkeypatch):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    seen: list[dict] = []

    def fake_get(path: str, bearer: str, params: dict | None = None):
        del bearer
        if path.startswith("/2/users/by/username/"):
            return _Resp({"data": {"id": "42"}})
        seen.append(dict(params or {}))
        return _Resp(
            {
                "data": [
                    {"created_at": f"2026-09-2{i}T00:00:00.000Z", "text": f"t{i}"}
                    for i in range(5)
                ],
                "meta": {"next_token": "more"},
            }
        )

    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_get", fake_get)
    rows = _x_api("Demo", since, enough=5)
    assert len(rows) == 5
    assert len(seen) == 1
    assert seen[0]["max_results"] == 5
    assert _x_api("Demo", since) is not None
    assert seen[-1]["max_results"] == 100


def test_kpi1_copy_capped_shows_at_least():
    verdict = evaluate_kpi1(handle="demo", count=5, unread=False, links=[], capped=True)
    assert "Original posts (30d): ≥5 (need ≥5)" in verdict["copy"]
    assert verdict["capped"] is True
    short = evaluate_kpi1(handle="demo", count=3, unread=False, links=[], capped=True)
    assert "Original posts (30d): 3 (need ≥5)" in short["copy"]
    assert short["capped"] is False


@pytest.mark.parametrize(
    ("kpi2", "posts", "capped"),
    [("https://x.com/demo/status/9", 6, True), ("", 6, True), ("", 5, False)],
)
def test_audit_reads_six_originals(monkeypatch, kpi2, posts, capped):
    from types import SimpleNamespace

    from bot import workflow_kpi1_twitter as mod

    asked: list[int | None] = []
    rows = [
        (datetime(2026, 10, 1 + i, tzinfo=SH), f"t{i}", {"id": str(i + 1)})
        for i in range(posts)
    ]

    def fake_fetch(handle, *, since, enough=None):
        del handle, since
        asked.append(enough)
        return "x_api", rows

    cfg = SimpleNamespace(
        workflow_project_name_field="项目名称 Project Name",
        workflow_base_app_token="app",
        workflow_progress_table_id="tbl",
    )
    monkeypatch.setattr("bot.workflow_kpi_write.kpi_checks_on_this_host", lambda: True)
    monkeypatch.setattr(
        mod,
        "find_wallet_row",
        lambda *_a: ("rec", {mod._TWITTER_FIELD_ALIASES[0]: "https://x.com/demo"}),
    )
    monkeypatch.setattr(mod, "fetch_timeline", fake_fetch)
    monkeypatch.setattr(mod, "now_shanghai", lambda: datetime(2026, 10, 10, tzinfo=SH))
    monkeypatch.setattr(mod, "maybe_write_kpi2_from_tweets", lambda *_a, **_k: "")
    monkeypatch.setattr(mod, "update_record", lambda *_a, **_k: None)
    fields = {"项目名称 Project Name": "Demo"}
    if kpi2:
        fields[mod._KPI2_LINK] = kpi2
    out = mod.audit_kpi1_for_fields("tok", cfg, "rec1", fields, project_name="Demo")
    assert asked == [6]
    assert out["passed"] is True
    assert out["capped"] is capped


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
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_api", lambda handle, start, **_kw: tweets)
    count, source = count_originals("demo", since=since)
    assert source == "x_api"
    assert count == 5


def test_count_originals_does_not_fall_back_when_x_api_fails(monkeypatch):
    since = datetime(2026, 9, 1, tzinfo=timezone.utc)
    monkeypatch.setenv("X_BEARER_TOKEN", "test")
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_api", lambda handle, start, **_kw: None)
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
    monkeypatch.setattr("bot.workflow_kpi1_twitter._x_api", lambda handle, start, **_kw: tweets)
    count, source, links = collect_originals("demo", since=since)
    assert source == "x_api"
    assert count == 2
    assert links == [
        "https://x.com/demo/status/5",
        "https://x.com/demo/status/4",
    ]


def test_mainnet_pr_live_on_chain_or_partnership():
    extra = {"id": "9"}
    assert is_mainnet_pr_tweet(
        "BanshanBook is live on Botchain mainnet today",
        extra,
        project_name="BanshanBook",
    )
    assert is_mainnet_pr_tweet(
        "Banshan × BOT Chain  Now live on BOT Chain Mainnet",
        extra,
        project_name="BanshanBook",
    )
    assert is_mainnet_pr_tweet(
        "Ezswap launched on Botchain mainnet",
        extra,
        project_name="ezswap",
    )
    assert is_mainnet_pr_tweet(
        "Ezswap go-live on Botchain",
        extra,
        project_name="ezswap",
    )
    assert is_mainnet_pr_tweet(
        "Ezswap partnership with Botchain",
        extra,
        project_name="ezswap",
    )
    assert is_mainnet_pr_tweet(
        "Ezswap partnership Botchain",
        extra,
        project_name="ezswap",
    )
    assert is_mainnet_pr_tweet(
        "Ezswap partnership with BotChain",
        extra,
        project_name="ezswap",
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
        "BanshanBook is live. We love Botchain",
        extra,
        project_name="BanshanBook",
    )
    assert not is_mainnet_pr_tweet(
        "BanshanBook partnership with Uniswap",
        extra,
        project_name="BanshanBook",
    )
    assert not is_mainnet_pr_tweet(
        "RT @x BanshanBook is live on Botchain mainnet",
        extra,
        project_name="BanshanBook",
    )
    assert tweet_has_project_name("go live with Banshan Book now", "BanshanBook")
    assert tweet_has_project_name(
        "Banshan × BOT Chain  Now live on BOT Chain Mainnet",
        "BanshanBook",
    )
    assert not tweet_has_project_name(
        "Books evolved. Now live on BOT Chain Mainnet",
        "BanshanBook",
    )
    assert not is_mainnet_pr_tweet(
        "Foo is live on Botchain mainnet",
        extra,
        project_name="FooChain",
    )


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


def test_parse_mainnet_pr_choice_keeps_listed_id():
    from bot.workflow_kpi1_twitter import parse_mainnet_pr_choice

    tweet_id, reason = parse_mainnet_pr_choice(
        '```json\n{"id":"20","reason":"live on BOT Chain"}\n```',
        {"20", "10"},
    )
    assert tweet_id == "20"
    assert reason == "live on BOT Chain"


def test_parse_mainnet_pr_choice_rejects_unknown_id():
    from bot.workflow_kpi1_twitter import parse_mainnet_pr_choice

    tweet_id, reason = parse_mainnet_pr_choice(
        '{"id":"https://x.com/a/status/999","reason":"guess"}',
        {"20"},
    )
    assert tweet_id == ""
    assert reason == "guess"
    empty, _reason = parse_mainnet_pr_choice(
        '{"id":"","reason":"none announce a launch"}',
        {"20"},
    )
    assert empty == ""


def test_mainnet_pr_prompt_counts_live_and_partnership():
    from bot.workflow_kpi1_twitter import mainnet_pr_prompt

    text = mainnet_pr_prompt(
        "BanshanBook",
        "banshanbook",
        [("20", "2026-09-20", "now live on BOT Chain")],
    )
    assert "live, go-live, or launched on BOT Chain" in text
    assert "partnership with BOT Chain" in text
    assert "id=20 date=2026-09-20" in text


def test_judge_skips_without_credentials(monkeypatch):
    from bot.workflow_kpi1_twitter import judge_mainnet_pr_url

    monkeypatch.setattr("bot.rag.resolve_llm_credentials", lambda config: None)

    class Cfg:
        llm_provider = "deepseek"
        llm_base_url = ""
        llm_model = ""

    url, reason = judge_mainnet_pr_url(
        Cfg(),
        project_name="BanshanBook",
        handle="banshanbook",
        rows=[
            (
                datetime(2026, 9, 20, tzinfo=timezone.utc),
                "BanshanBook is live on Botchain",
                {"id": "20"},
            )
        ],
        since=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert url == ""
    assert reason == ""


def test_judge_api_failure_returns_empty(monkeypatch):
    from bot.workflow_kpi1_twitter import judge_mainnet_pr_url

    class Creds:
        api_key = "k"
        base_url = "https://example.invalid"
        model = "test"

    monkeypatch.setattr("bot.rag.resolve_llm_credentials", lambda config: Creds())

    def boom():
        raise RuntimeError("down")

    monkeypatch.setattr("bot.rag._get_openai_client_class", boom)

    class Cfg:
        pass

    url, reason = judge_mainnet_pr_url(
        Cfg(),
        project_name="BanshanBook",
        handle="banshanbook",
        rows=[
            (
                datetime(2026, 9, 20, tzinfo=timezone.utc),
                "partnership with BOT Chain",
                {"id": "20"},
            )
        ],
        since=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert url == ""
    assert reason == ""


def test_maybe_write_kpi2_skips_filled_cell(monkeypatch):
    from bot.workflow_kpi1_twitter import maybe_write_kpi2_from_tweets

    called: list[object] = []
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter.update_record",
        lambda *args, **kwargs: called.append(args),
    )

    def judge_should_not_run(*_args, **_kwargs):
        raise AssertionError("filled KPI 2 must not call the model")

    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter.judge_mainnet_pr_url",
        judge_should_not_run,
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
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter.judge_mainnet_pr_url",
        lambda *args, **kwargs: (
            "https://x.com/banshanbook/status/20",
            "live on BOT Chain",
        ),
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


def test_maybe_write_kpi2_leaves_empty_when_model_declines(monkeypatch):
    from bot.workflow_kpi1_twitter import maybe_write_kpi2_from_tweets

    patches: list[dict] = []
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter.update_record",
        lambda token, app, table, rid, fields: patches.append(fields),
    )
    monkeypatch.setattr(
        "bot.workflow_kpi1_twitter.judge_mainnet_pr_url",
        lambda *args, **kwargs: ("", "no launch tweet"),
    )

    class Cfg:
        pr_capture_link_field = "KPI 2 - PR 新闻链接验证"
        workflow_base_app_token = "app"
        workflow_progress_table_id = "tbl"

    url = maybe_write_kpi2_from_tweets(
        "tok",
        Cfg(),
        "rec1",
        {},
        project_name="BanshanBook",
        handle="banshanbook",
        rows=[
            (
                datetime(2026, 9, 20, tzinfo=timezone.utc),
                "gm",
                {"id": "20"},
            )
        ],
        since=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert url == ""
    assert patches == []
