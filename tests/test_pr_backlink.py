from __future__ import annotations

import asyncio

from bot.workflow_pr_backlink import (
    dispatch_backlinks,
    parse_backlink_trigger,
    pending_backlinks,
    plain_url,
    resolve_project_chat,
)

BACKLINK = "回链 （将回链填入该格时，回链链接将会被自动推送到项目方所在的 TG 群）"


def _row(record_id: str, project: str, backlink: str = "", pr: str = "") -> dict:
    return {
        "record_id": record_id,
        "fields": {
            "项目方": project,
            "主网上线PR链接": pr,
            BACKLINK: backlink,
        },
    }


def test_plain_url_unwraps_markdown_and_rejects_plain_text():
    assert plain_url("[site](https://example.com/a)") == "https://example.com/a"
    assert plain_url("see https://example.com/b.") == "https://example.com/b"
    assert plain_url("还没写") == ""
    assert plain_url("") == ""


def test_only_a_new_backlink_is_pending():
    rows = [
        _row("rec_empty", "Empty", pr="https://x.com/a/status/1"),
        _row("rec_same", "Same", backlink="https://x.com/a/status/2"),
        _row("rec_new", "New", backlink="https://x.com/a/status/3"),
        _row("rec_changed", "Changed", backlink="https://x.com/a/status/9"),
    ]
    sent = {
        "rec_same": "https://x.com/a/status/2",
        "rec_changed": "https://x.com/a/status/8",
    }
    pending = pending_backlinks(rows, sent)
    assert [item["record_id"] for item in pending] == ["rec_new", "rec_changed"]
    assert pending[1]["url"] == "https://x.com/a/status/9"


def test_the_same_url_on_two_rows_both_send():
    url = "https://x.com/news/status/1"
    rows = [
        _row("rec_a", "Alpha", backlink=url),
        _row("rec_b", "Beta", backlink=url),
    ]
    pending = pending_backlinks(rows, {})
    assert [item["project"] for item in pending] == ["Alpha", "Beta"]
    assert {item["url"] for item in pending} == {url}


def test_progress_tg_id_beats_a_title():
    progress = [
        {
            "record_id": "rec_live",
            "fields": {
                "项目名称 Project Name": "AgentForge",
                "TG群ID": "-100111",
            },
        }
    ]
    titles = {-100222: "AgentForge delivery"}
    chat_id, reason = resolve_project_chat(
        "AgentForge",
        progress,
        titles,
        name_field="项目名称 Project Name",
        chat_field="TG群ID",
    )
    assert chat_id == -100111
    assert reason == "progress TG id"


def _title_matcher(project: str, titles: dict[int, str]) -> tuple[int | None, str]:
    hits = [chat_id for chat_id, title in titles.items() if title == project]
    if len(hits) == 1:
        return hits[0], "title match"
    if len(hits) > 1:
        return None, f"ambiguous title matches: {hits}"
    return None, "no fuzzy title match"


def test_title_match_when_the_progress_row_has_no_tg_id():
    progress = [
        {
            "record_id": "rec_live",
            "fields": {"项目名称 Project Name": "Purse Pay", "TG群ID": ""},
        }
    ]
    chat_id, reason = resolve_project_chat(
        "Purse Pay",
        progress,
        {-100333: "Purse Pay"},
        name_field="项目名称 Project Name",
        chat_field="TG群ID",
        title_matcher=_title_matcher,
    )
    assert chat_id == -100333
    assert reason == "title match"


def test_ambiguous_titles_do_not_send():
    chat_id, reason = resolve_project_chat(
        "Flow",
        [],
        {-1001: "Flow", -1002: "Flow"},
        name_field="项目名称 Project Name",
        chat_field="TG群ID",
        title_matcher=_title_matcher,
    )
    assert chat_id is None
    assert "ambiguous" in reason


class _FakeClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def test_dispatch_sends_the_url_and_remembers_it():
    client = _FakeClient()
    pending = [
        {"record_id": "rec_a", "project": "Alpha", "url": "https://x.com/a/status/1"},
        {"record_id": "rec_b", "project": "Beta", "url": "https://x.com/a/status/1"},
    ]
    progress = [
        {"record_id": "p1", "fields": {"项目名称 Project Name": "Alpha", "TG群ID": "-1001"}},
        {"record_id": "p2", "fields": {"项目名称 Project Name": "Beta", "TG群ID": "-1002"}},
    ]
    sent: dict[str, str] = {}
    results = asyncio.run(
        dispatch_backlinks(
            client,
            pending,
            progress,
            {},
            sent,
            name_field="项目名称 Project Name",
            chat_field="TG群ID",
        )
    )
    assert client.sent == [
        (-1001, "https://x.com/a/status/1"),
        (-1002, "https://x.com/a/status/1"),
    ]
    assert sent == {
        "rec_a": "https://x.com/a/status/1",
        "rec_b": "https://x.com/a/status/1",
    }
    assert all(item["sent"] for item in results)
    again = pending_backlinks(
        [
            _row("rec_a", "Alpha", backlink="https://x.com/a/status/1"),
            _row("rec_b", "Beta", backlink="https://x.com/a/status/1"),
        ],
        sent,
    )
    assert again == []


def test_unmatched_project_is_not_marked_sent():
    client = _FakeClient()
    sent: dict[str, str] = {}
    results = asyncio.run(
        dispatch_backlinks(
            client,
            [{"record_id": "rec_x", "project": "Missing", "url": "https://x.com/a/status/1"}],
            [],
            {},
            sent,
            name_field="项目名称 Project Name",
            chat_field="TG群ID",
            title_matcher=_title_matcher,
        )
    )
    assert client.sent == []
    assert sent == {}
    assert results[0]["sent"] is False


def test_trigger_reads_the_backlink_and_ignores_other_tables():
    parsed = parse_backlink_trigger(
        {
            "table_id": "tbllA25Mz66e8wpv",
            "record_id": "rec_a",
            "项目方": "Alpha",
            "回链": "https://x.com/a/status/1",
        }
    )
    assert parsed["url"] == "https://x.com/a/status/1"
    assert parsed["project"] == "Alpha"
    assert parse_backlink_trigger(
        {"table_id": "tblsPBJW1HUmkM6X", "record_id": "rec_x", "回链": "https://x.com/a/status/1"}
    ) is None
    assert parse_backlink_trigger(
        {
            "event": {
                "table_id": "tbllA25Mz66e8wpv",
                "action_list": [
                    {
                        "record_id": "rec_b",
                        "after_value": [
                            {"field_id": "fld9F9qmk0", "field_name": "官网", "field_value": "https://a.example"}
                        ],
                    }
                ],
            }
        }
    ) is None


def test_dry_run_does_not_send_or_remember():
    client = _FakeClient()
    sent: dict[str, str] = {}
    results = asyncio.run(
        dispatch_backlinks(
            client,
            [{"record_id": "rec_a", "project": "Alpha", "url": "https://x.com/a/status/1"}],
            [{"record_id": "p1", "fields": {"项目名称 Project Name": "Alpha", "TG群ID": "-1001"}}],
            {},
            sent,
            name_field="项目名称 Project Name",
            chat_field="TG群ID",
            dry_run=True,
        )
    )
    assert client.sent == []
    assert sent == {}
    assert results[0]["dry_run"] is True
    assert results[0]["chat_id"] == -1001
