from __future__ import annotations

import asyncio

from bot.workflow_mark_live import (
    MISSING_SITE_REMINDER,
    live_site_missing,
    peek_mark_live_site_pending,
    pop_mark_live_site_pending,
    resolve_mark_live_site_reply,
    save_mark_live_site_pending,
)


class _Cfg:
    workflow_live_link_field = "已上线链接🔗"
    workflow_base_app_token = "app"
    workflow_progress_table_id = "tbl"


def test_live_site_missing():
    assert live_site_missing(_Cfg(), {})
    assert live_site_missing(_Cfg(), {"已上线链接🔗": ""})
    assert live_site_missing(_Cfg(), {"已上线链接🔗": "not-a-url"})
    assert not live_site_missing(
        _Cfg(), {"已上线链接🔗": {"link": "https://live.example/"}}
    )


def test_missing_site_reminder_is_english():
    assert "website field is empty" in MISSING_SITE_REMINDER.lower()
    assert "http://" in MISSING_SITE_REMINDER.lower() or "https://" in MISSING_SITE_REMINDER


def test_resolve_mark_live_site_reply_writes_url(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "bot.workflow_mark_live.SITE_PENDING_PATH", tmp_path / "site_pending.json"
    )
    writes: list[tuple[str, dict]] = []
    save_mark_live_site_pending(
        chat_id=11,
        reply_msg_id=22,
        record_id="rec_a",
        project_name="Alpha",
    )
    monkeypatch.setenv("LARK_APP_ID", "id")
    monkeypatch.setenv("LARK_APP_SECRET", "secret")
    monkeypatch.setattr(
        "bot.workflow_mark_live.get_tenant_access_token", lambda *_a, **_k: "tok"
    )
    monkeypatch.setattr(
        "bot.workflow_mark_live.update_record",
        lambda token, app, table, rid, payload: writes.append((rid, payload)),
    )

    assert (
        asyncio.run(
            resolve_mark_live_site_reply(
                _Cfg(), chat_id=11, quoted_msg_id=999, reply_text="https://x.example/"
            )
        )
        is None
    )

    ask = asyncio.run(
        resolve_mark_live_site_reply(
            _Cfg(), chat_id=11, quoted_msg_id=22, reply_text="please check"
        )
    )
    assert ask is not None
    assert "http://" in ask.lower()
    assert peek_mark_live_site_pending(11, 22) is not None

    ok = asyncio.run(
        resolve_mark_live_site_reply(
            _Cfg(),
            chat_id=11,
            quoted_msg_id=22,
            reply_text="Official site: https://alpha.example/app",
        )
    )
    assert ok is not None
    assert "Website saved" in ok
    assert "mark live again" in ok.lower()
    assert writes == [
        (
            "rec_a",
            {
                "已上线链接🔗": {
                    "link": "https://alpha.example/app",
                    "text": "https://alpha.example/app",
                }
            },
        )
    ]
    assert pop_mark_live_site_pending(11, 22) is None
