from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from bot.folder_auto_add import _is_stale_upgraded_chat, _resolve_live_chat


def test_live_megagroup_is_not_stale():
    chat = SimpleNamespace(deactivated=False, title="AetherisDAO | BOT Chain")
    assert _is_stale_upgraded_chat(chat) is False


def test_deactivated_leftover_is_stale():
    chat = SimpleNamespace(
        deactivated=True,
        migrated_to=object(),
        title="AetherisDAO | BOT Chain",
    )
    assert _is_stale_upgraded_chat(chat) is True


def test_resolve_does_not_fall_back_to_deactivated_id():
    stale = SimpleNamespace(
        deactivated=True,
        migrated_to=object(),
        title="AetherisDAO | BOT Chain",
        id=-5305812455,
    )

    class Client:
        async def get_entity(self, _peer):
            raise RuntimeError("gone")

        async def get_input_entity(self, _peer):
            raise AssertionError("must not add leftover chat")

    async def _run():
        try:
            await _resolve_live_chat(Client(), stale)
        except RuntimeError:
            return
        raise AssertionError("expected resolve to fail instead of using leftover id")

    asyncio.run(_run())


def test_resolve_prefers_live_megagroup():
    live = SimpleNamespace(deactivated=False, title="AetherisDAO | BOT Chain", id=3672902111)
    stale = SimpleNamespace(
        deactivated=True,
        migrated_to=object(),
        title="AetherisDAO | BOT Chain",
        id=-5305812455,
    )

    class Client:
        async def get_entity(self, _peer):
            return live

        async def get_input_entity(self, chat):
            return SimpleNamespace(peer=chat)

    async def _run():
        with patch("bot.folder_auto_add.utils.get_peer_id", side_effect=lambda x: x.id):
            resolved, chat_id, _peer = await _resolve_live_chat(Client(), stale)
        assert resolved is live
        assert chat_id == live.id

    asyncio.run(_run())
