from __future__ import annotations

from datetime import datetime, timezone

from bot.workflow_kpi1_twitter import (
    SH,
    _utc_stamp,
    _x_api,
    count_originals,
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
