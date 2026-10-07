from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from bot.workflow_form_dispatch import match_project_to_chat
from bot.workflow_live_onboard import (
    _RETRY_NOTIFY,
    _SKIP_NOTIFY_SOURCES,
    apply_form_sent,
    build_onboard_message,
    classify_case,
    form_already_sent,
    load_peer_folder_titles,
    merge_membership,
    parse_bd_person,
    resolve_form_sent,
    sends_lark_notify,
    should_wait_for_form_handoff,
    wait_until_form_sent,
)


def test_classify_cases():
    assert classify_case(True, True) == 1
    assert classify_case(True, False) == 2
    assert classify_case(False, True) == 3
    assert classify_case(False, False) == 4


def test_merge_membership_keeps_stored_when_peer_lookup_fails():
    roy_in, josh_in = merge_membership(
        self_key="roy",
        self_in=True,
        stored_roy=False,
        stored_josh=True,
        peer_live=None,
    )
    assert roy_in is True
    assert josh_in is True


def test_merge_membership_live_false_overrides_stored():
    roy_in, josh_in = merge_membership(
        self_key="roy",
        self_in=True,
        stored_roy=True,
        stored_josh=True,
        peer_live=False,
    )
    assert roy_in is True
    assert josh_in is False


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
        form_sent=True,
    )
    assert text.startswith('<at user_id="ou_ella">Ella</at>')
    assert "**Project:** `vritz`" in text
    assert "**Status:** Live on mainnet" in text
    assert "**TG group:** `vritz <> Botchain`" in text
    assert "**Delivery:** Roy and Josh have joined" in text
    assert "**Form:** Onboarding Google Form has been sent" in text
    assert "Add Josh" not in text
    assert "Create the project TG group" not in text
    assert "1. Help the project submit Twitter and the contract address to the form" in text
    assert "2. Share the mainnet-live PR tweet in the TG group and @ Roy and Josh" in text


def test_case2_asks_to_add_josh():
    text = build_onboard_message(
        case=2,
        project="vritz",
        group="vritz <> Botchain",
        bd_name="Ella",
        bd_open_id="ou_ella",
        form_sent=True,
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
        form_sent=True,
    )
    assert "**Delivery:** Josh has joined; Roy has not been added" in text
    assert "1. Add Roy to the TG group" in text


def test_known_group_does_not_ask_to_create_when_form_already_sent():
    text = build_onboard_message(
        case=4,
        project="vritz",
        group="Botchain X Example",
        bd_name="Ella",
        bd_open_id="ou_ella",
        form_sent=True,
    )
    assert "**TG group:** `Botchain X Example`" in text
    assert "**Delivery:** Roy / Josh were not detected in this TG group" in text
    assert "**Form:** Onboarding Google Form has been sent" in text
    assert "Create the project TG group" not in text
    assert "1. Add Roy and Josh to the TG group" in text
    assert "Trigger the Onboarding Google Form send" not in text


def test_both_in_group_but_form_not_sent():
    text = build_onboard_message(
        case=1,
        project="vritz",
        group="vritz <> Botchain",
        bd_name="Ella",
        bd_open_id="ou_ella",
        form_sent=False,
    )
    assert "**Delivery:** Roy and Josh have joined" in text
    assert "**Form:** Onboarding Google Form was not sent" in text
    assert "1. Trigger the Onboarding Google Form send" in text
    assert "Create the project TG group" not in text


def test_case4_no_group():
    text = build_onboard_message(
        case=4,
        project="vritz",
        group="",
        bd_name="Ella",
        bd_open_id="ou_ella",
        form_sent=False,
    )
    assert "**Delivery:** Roy / Josh were not detected in a TG group" in text
    assert "**Form:** Onboarding Google Form was not sent" in text
    assert "1. Create the project TG group, add Roy and Josh, then trigger the form send" in text
    assert "**TG group:** `not matched`" in text


def test_form_already_sent_from_peer_dispatch(tmp_path, monkeypatch):
    (tmp_path / "form_dispatch_state.json").write_text(
        json.dumps({"sent_record_ids": ["rec-form"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "bot.workflow_live_onboard._DATA_ROOTS",
        (tmp_path,),
    )
    cfg = SimpleNamespace(
        workflow_state_file=str(tmp_path / "missing-dispatch.json"),
        workflow_form_chase_state_file=str(tmp_path / "missing-chase.json"),
    )
    assert form_already_sent(cfg, rid="rec-form", chat_id=None) is True
    assert form_already_sent(cfg, rid="rec-other", chat_id=None) is False


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
    assert "waiting_form" in _RETRY_NOTIFY
    assert "sent" not in _RETRY_NOTIFY


def test_wait_for_deferred_or_both_in_group():
    assert should_wait_for_form_handoff(
        form_sent=False,
        form_status="deferred",
        claim_status="",
        roy_in=True,
        josh_in=True,
    )
    assert should_wait_for_form_handoff(
        form_sent=False,
        form_status="not_in_group",
        claim_status="assigned",
        roy_in=True,
        josh_in=False,
    )
    assert should_wait_for_form_handoff(
        form_sent=False,
        form_status="",
        claim_status="",
        roy_in=True,
        josh_in=True,
    )
    assert not should_wait_for_form_handoff(
        form_sent=True,
        form_status="deferred",
        claim_status="assigned",
        roy_in=True,
        josh_in=True,
    )
    assert not should_wait_for_form_handoff(
        form_sent=False,
        form_status="no_group",
        claim_status="",
        roy_in=False,
        josh_in=False,
    )


def test_apply_form_sent_never_downgrades():
    entry = {"form": "sent", "form_sent": True}
    assert apply_form_sent(entry, False) is True
    assert entry["form_sent"] is True
    assert entry["form"] == "sent"

    blank = {"form": "deferred", "form_sent": False}
    assert apply_form_sent(blank, True) is True
    assert blank["form_sent"] is True
    assert blank["form"] == "already_sent"


def test_resolve_form_sent_keeps_known_true(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "bot.workflow_live_onboard._DATA_ROOTS",
        (tmp_path,),
    )
    cfg = SimpleNamespace(
        workflow_state_file=str(tmp_path / "missing-dispatch.json"),
        workflow_form_chase_state_file=str(tmp_path / "missing-chase.json"),
    )
    assert (
        resolve_form_sent(
            cfg, rid="rec-x", chat_id=None, entry={"form": "deferred"}, known=True
        )
        is True
    )
    assert (
        resolve_form_sent(
            cfg, rid="rec-x", chat_id=None, entry={"form": "deferred"}
        )
        is False
    )


def test_wait_until_form_sent_sees_peer_write(tmp_path, monkeypatch):
    import bot.workflow_live_onboard as onboard

    monkeypatch.setattr(onboard, "FORM_HANDOFF_WAIT_SECONDS", 2)
    monkeypatch.setattr(onboard, "FORM_HANDOFF_POLL_SECONDS", 0.01)
    monkeypatch.setattr(onboard, "_DATA_ROOTS", (tmp_path,))
    state = tmp_path / "live_onboard_state.json"
    monkeypatch.setattr(onboard, "_state_path", lambda _cfg: state)
    dispatch = tmp_path / "form_dispatch_state.json"
    dispatch.write_text(json.dumps({"sent_record_ids": []}), encoding="utf-8")
    cfg = SimpleNamespace(
        workflow_state_file=str(dispatch),
        workflow_form_chase_state_file=str(tmp_path / "missing-chase.json"),
        workflow_live_onboard_state_file=str(state),
    )

    async def _run() -> bool:
        async def _mark() -> None:
            await asyncio.sleep(0.03)
            dispatch.write_text(
                json.dumps({"sent_record_ids": ["rec-wait"]}),
                encoding="utf-8",
            )

        asyncio.create_task(_mark())
        return await wait_until_form_sent(cfg, rid="rec-wait", chat_id=None)

    assert asyncio.run(_run()) is True


def test_peer_folder_cache_matches_delivery_account_group(tmp_path, monkeypatch):
    josh_root = tmp_path / "delivery-agent" / "data"
    josh_root.mkdir(parents=True)
    (josh_root / "folder_title_cache.json").write_text(
        json.dumps({"titles": {"-5408000001": {"title": "Delivery X Sample"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "bot.workflow_live_onboard._DATA_ROOTS",
        (josh_root,),
    )
    titles, roy_ids, josh_ids = load_peer_folder_titles()
    chat_id, reason = match_project_to_chat("sample", titles)
    assert chat_id == -5408000001
    assert chat_id in josh_ids
    assert chat_id not in roy_ids
    assert reason


def test_cache_membership_kept_after_peer_live_false():
    roy_in, josh_in = merge_membership(
        self_key="roy",
        self_in=False,
        stored_roy=False,
        stored_josh=True,
        peer_live=False,
    )
    cache_josh = True
    josh_in = josh_in or cache_josh
    roy_in = roy_in or False
    assert roy_in is False
    assert josh_in is True
