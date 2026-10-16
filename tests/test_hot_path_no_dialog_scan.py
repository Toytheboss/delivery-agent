from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from bot.workflow_live_onboard import resolve_project_chat
from bot.workflow_mark_live import _apply_mark_live


class _Scope:
    chat_ids: set[int] = set()

    async def refresh(self) -> set[int]:
        raise AssertionError("hot path must not GetDialogs via scope.refresh")


def test_resolve_project_chat_uses_preferred_without_scan():
    cfg = SimpleNamespace(workflow_tg_chat_id_field="TG群ID")

    async def boom(*_args, **_kwargs):
        raise AssertionError("hot path must not GetDialogs via _dialog_title_map")

    with patch("bot.workflow_live_onboard._dialog_title_map", boom), patch(
        "bot.workflow_live_onboard.build_folder_title_map", boom
    ), patch("bot.workflow_live_onboard.load_peer_folder_titles", boom):
        chat_id, title, reason = asyncio.run(
            resolve_project_chat(
                client=None,
                config=cfg,
                scope=_Scope(),
                name="Omikuji",
                fields={},
                preferred_chat_id=-5583098547,
                preferred_chat_title="Omikuji x BOT Chain",
            )
        )
    assert chat_id == -5583098547
    assert title == "Omikuji x BOT Chain"
    assert reason == "preferred chat"


def test_resolve_project_chat_uses_lark_id_without_scan():
    cfg = SimpleNamespace(workflow_tg_chat_id_field="TG群ID")

    async def boom(*_args, **_kwargs):
        raise AssertionError("hot path must not GetDialogs")

    async def no_entity(*_args, **_kwargs):
        return False, ""

    with patch("bot.workflow_live_onboard._dialog_title_map", boom), patch(
        "bot.workflow_live_onboard.build_folder_title_map", boom
    ), patch("bot.workflow_live_onboard.account_in_chat", no_entity):
        chat_id, _title, reason = asyncio.run(
            resolve_project_chat(
                client=None,
                config=cfg,
                scope=_Scope(),
                name="Omikuji",
                fields={"TG群ID": "-5583098547"},
                preferred_chat_id=None,
                preferred_chat_title=None,
            )
        )
    assert chat_id == -5583098547
    assert reason == "lark TG群ID field"


def test_apply_mark_live_does_not_refresh_scope(monkeypatch):
    cfg = SimpleNamespace(
        workflow_status_field="项目状态",
        workflow_trigger_status="BOT主网上线 Live on BOT Chain Mainnet",
        workflow_mark_live_also_send_form=True,
        workflow_google_form_url="https://form.example",
        workflow_base_app_token="app",
        workflow_progress_table_id="tbl",
        workflow_tg_chat_id_field="",
    )
    scope = _Scope()
    called: dict[str, object] = {}

    async def fake_speaker(*_args, **_kwargs):
        return "josh"

    async def fake_process(client, config, live_scope, **kwargs):
        called["scope"] = live_scope
        called["preferred"] = kwargs.get("preferred_chat_id")
        return {"form": "already_sent", "logo": "disabled"}

    async def fake_write_tg(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(
        "bot.workflow_mark_live._prepare_mark_live_form_speaker", fake_speaker
    )
    monkeypatch.setattr("bot.workflow_mark_live.process_live_project", fake_process)
    monkeypatch.setattr("bot.workflow_mark_live._maybe_write_tg_chat_id", fake_write_tg)
    monkeypatch.setattr(
        "bot.workflow_logo_fill.logo_fill_allowed", lambda _cfg: False
    )

    text = asyncio.run(
        _apply_mark_live(
            client=None,
            config=cfg,
            token="tok",
            record_id="rec1",
            project_name="Omikuji",
            fields={"项目状态": "BOT主网上线 Live on BOT Chain Mainnet"},
            chat_id=-5583098547,
            chat_title="Omikuji x BOT Chain",
            scope=scope,
        )
    )
    assert "already live" in text
    assert called["scope"] is scope
    assert called["preferred"] == -5583098547
