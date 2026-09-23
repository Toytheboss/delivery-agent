from __future__ import annotations

import time

from bot.workflow_lark_bridge import (
    find_session_by_bridge,
    format_inbound_push,
    match_inbound,
    session_active,
    upsert_session,
)


def test_push_copy_is_name_then_body():
    assert format_inbound_push("Lighter", "看到了") == "Lighter：看到了"
    assert format_inbound_push("张三", "ok", group_name="交付群") == "张三（交付群）：ok"
    assert format_inbound_push("Lighter", "") == "Lighter：[非文字，先只转文字]"


def test_session_expires_after_24_hours(monkeypatch, tmp_path):
    monkeypatch.setenv("LARK_RELAY_SESSIONS", str(tmp_path / "sessions.json"))
    now = 1_000_000.0
    session = upsert_session(
        kind="user",
        peer_id="ou_lighter",
        peer_name="Lighter",
        roy_chat_id="oc_roy",
        outbound_message_id="om_out",
        now=now,
    )
    assert session_active(session, now + 23 * 3600)
    assert not session_active(session, now + 24 * 3600 + 1)


def test_p2p_inbound_only_after_send_to(monkeypatch, tmp_path):
    monkeypatch.setenv("LARK_RELAY_SESSIONS", str(tmp_path / "sessions.json"))
    now = time.time()
    upsert_session(
        kind="user",
        peer_id="ou_lighter",
        peer_name="Lighter",
        roy_chat_id="oc_roy",
        outbound_message_id="om_out",
        now=now,
    )
    message = {"chat_type": "p2p", "chat_id": "oc_p2p", "message_id": "om_in"}
    sender = {"sender_id": {"open_id": "ou_lighter"}, "sender_type": "user"}
    hit = match_inbound(message, sender, now=now)
    assert hit is not None
    assert hit["peer_name"] == "Lighter"

    other = {"sender_id": {"open_id": "ou_stranger"}, "sender_type": "user"}
    assert match_inbound(message, other, now=now) is None


def test_group_inbound_only_when_replying_to_bot(monkeypatch, tmp_path):
    monkeypatch.setenv("LARK_RELAY_SESSIONS", str(tmp_path / "sessions.json"))
    now = time.time()
    upsert_session(
        kind="group",
        peer_id="oc_group",
        peer_name="运营群",
        roy_chat_id="oc_roy",
        outbound_message_id="om_out",
        now=now,
    )
    sender = {"sender_id": {"open_id": "ou_jasper"}, "sender_type": "user"}
    reply = {
        "chat_type": "group",
        "chat_id": "oc_group",
        "parent_id": "om_out",
        "message_id": "om_in",
    }
    assert match_inbound(reply, sender, now=now) is not None

    chatter = {
        "chat_type": "group",
        "chat_id": "oc_group",
        "parent_id": "",
        "message_id": "om_other",
    }
    assert match_inbound(chatter, sender, now=now) is None


def test_roy_reply_maps_to_the_push(monkeypatch, tmp_path):
    monkeypatch.setenv("LARK_RELAY_SESSIONS", str(tmp_path / "sessions.json"))
    now = time.time()
    upsert_session(
        kind="user",
        peer_id="ou_lighter",
        peer_name="Lighter",
        roy_chat_id="oc_roy",
        outbound_message_id="om_out",
        now=now,
    )
    from bot.workflow_lark_bridge import _touch

    session = find_session_by_bridge("om_push")
    assert session is None
    live = upsert_session(
        kind="user",
        peer_id="ou_lighter",
        peer_name="Lighter",
        roy_chat_id="oc_roy",
        now=now,
    )
    _touch(live, bridge_message_id="om_push", last_peer_message_id="om_in", now=now)
    found = find_session_by_bridge("om_push")
    assert found is not None
    assert found["peer_id"] == "ou_lighter"
    assert found["last_peer_message_id"] == "om_in"
