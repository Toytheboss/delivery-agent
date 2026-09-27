from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.workflow_live_onboard import (
    _RETRY_NOTIFY,
    _SKIP_NOTIFY_SOURCES,
    build_onboard_message,
    classify_case,
    lookup_live_membership,
    merge_form_sender_into_membership,
    parse_bd_person,
    sends_lark_notify,
)


def test_classify_cases():
    assert classify_case(True, True) == 1
    assert classify_case(True, False) == 2
    assert classify_case(False, True) == 3
    assert classify_case(False, False) == 4


def test_parse_bd_person_from_user_field():
    oid, name = parse_bd_person(
        {"BD": [{"id": "ou_ella", "name": "Ella"}]},
        "BD",
    )
    assert oid == "ou_ella"
    assert name == "Ella"


def test_case1_message_uses_group_title_and_at():
    text = build_onboard_message(
        case=1,
        project="vritz",
        group="vritz <> Botchain",
        bd_name="Ella",
        bd_open_id="ou_ella",
    )
    assert text.startswith('<at user_id="ou_ella">Ella</at>')
    assert "**Project:** `vritz`" in text
    assert "**Status:** Live on mainnet" in text
    assert "**TG group:** `vritz <> Botchain`" in text
    assert "**Delivery:** Roy and Josh have joined" in text
    assert "**Form:** Onboarding Google Form has been sent" in text
    assert "Add Josh" not in text
    assert "1. Help the project submit Twitter and the contract address to the form" in text
    assert "2. Share the mainnet-live PR tweet in the TG group and @ Roy and Josh" in text


def test_case2_asks_to_add_josh():
    text = build_onboard_message(
        case=2,
        project="vritz",
        group="vritz <> Botchain",
        bd_name="Ella",
        bd_open_id="ou_ella",
    )
    assert "**Delivery:** Roy has joined; Josh has not been added" in text
    assert "1. Add Josh to the TG group" in text


def test_case3_asks_to_add_roy():
    text = build_onboard_message(
        case=3,
        project="vritz",
        group="vritz <> Botchain",
        bd_name="Ella",
        bd_open_id="ou_ella",
    )
    assert "**Delivery:** Josh has joined; Roy has not been added" in text
    assert "1. Add Roy to the TG group" in text


def test_case4_form_not_sent():
    text = build_onboard_message(
        case=4,
        project="vritz",
        group="",
        bd_name="Ella",
        bd_open_id="ou_ella",
    )
    assert "**Delivery:** Roy / Josh were not detected in a TG group" in text
    assert "**Form:** Onboarding Google Form was not sent" in text
    assert "1. Create the project TG group, add Roy and Josh, then trigger the form send" in text
    assert "**TG group:** `vritz`" in text


def test_only_roy_sends_lark_notify():
    class Cfg:
        def __init__(self, account: str, replies: bool = False):
            self.workflow_live_onboard_account = account
            self.group_replies_enabled = replies

    assert sends_lark_notify(Cfg("roy")) is True
    assert sends_lark_notify(Cfg("josh")) is False
    assert sends_lark_notify(Cfg("", replies=True)) is True
    assert sends_lark_notify(Cfg("", replies=False)) is False


def test_join_catchup_does_not_send_live_notify():
    assert "join_catchup" in _SKIP_NOTIFY_SOURCES
    assert "startup_catchup" in _SKIP_NOTIFY_SOURCES


def test_retry_covers_stuck_scheduled():
    assert "scheduled" in _RETRY_NOTIFY
    assert "need_roy" in _RETRY_NOTIFY
    assert "sending" in _RETRY_NOTIFY
    assert "sent" not in _RETRY_NOTIFY


def test_merge_form_sender_does_not_invent_josh():
    roy_in, josh_in = merge_form_sender_into_membership(
        False,
        False,
        form_status="sent",
        form_by="roy",
    )
    assert roy_in is True
    assert josh_in is False


def test_merge_keeps_live_josh_lookup():
    roy_in, josh_in = merge_form_sender_into_membership(
        True,
        True,
        form_status="sent",
        form_by="roy",
    )
    assert roy_in is True
    assert josh_in is True


def test_lookup_live_membership_checks_josh_on_roy_account():
    cfg = SimpleNamespace(
        workflow_live_onboard_account="roy",
        group_replies_enabled=True,
    )

    async def _run():
        with patch(
            "bot.workflow_live_onboard.account_in_chat",
            AsyncMock(return_value=(True, "turingscoutnew&botchain")),
        ) as self_lookup, patch(
            "bot.workflow_live_onboard.peer_account_in_chat",
            AsyncMock(return_value=True),
        ) as peer_lookup:
            roy_in, josh_in = await lookup_live_membership(
                object(), -100123, config=cfg
            )
            assert roy_in is True
            assert josh_in is True
            self_lookup.assert_awaited_once()
            peer_lookup.assert_awaited_once()
            assert peer_lookup.await_args.args[2] == "josh"

    asyncio.run(_run())


def test_lookup_live_membership_can_find_josh_when_shared_state_was_false():
    cfg = SimpleNamespace(
        workflow_live_onboard_account="roy",
        group_replies_enabled=True,
    )

    async def _run():
        with patch(
            "bot.workflow_live_onboard.account_in_chat",
            AsyncMock(return_value=(True, "g")),
        ), patch(
            "bot.workflow_live_onboard.peer_account_in_chat",
            AsyncMock(return_value=True),
        ):
            assert await lookup_live_membership(object(), -1, config=cfg) == (
                True,
                True,
            )

    asyncio.run(_run())
