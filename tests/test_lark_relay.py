from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from bot.workflow_lark_relay import (
    choose_target,
    claim_message,
    mention_users,
    owner_open_ids,
    parse_relay_command,
    substitute_mentions,
    target_from_mentions,
)


def test_parse_uses_the_last_line_as_the_command():
    parsed = parse_relay_command("请看这份文档\nhttps://example.com/doc\nsend to Brian Wong")
    assert parsed == ("请看这份文档\nhttps://example.com/doc", "Brian Wong")
    assert parse_relay_command("send to Brian Wong") is None
    assert parse_relay_command("hello") is None


def test_exact_person_beats_a_partial_group():
    users = [{"kind": "user", "id": "ou_b", "name": "Brian Wong"}]
    groups = [{"kind": "group", "id": "oc_g", "name": "Brian delivery"}]
    picked, _ = choose_target(users, groups, "Brian Wong")
    assert picked["id"] == "ou_b"


def test_unique_partial_group():
    groups = [{"kind": "group", "id": "oc_g", "name": "交付 & 技术"}]
    picked, _ = choose_target([], groups, "交付")
    assert picked["kind"] == "group"


def test_ambiguous_names_do_not_pick():
    users = [
        {"kind": "user", "id": "ou_1", "name": "Brian Wong"},
        {"kind": "user", "id": "ou_2", "name": "Brian Lee"},
    ]
    picked, found = choose_target(users, [], "Brian")
    assert picked is None
    assert len(found) == 2


def test_person_and_group_with_the_same_name_stay_ambiguous():
    users = [{"kind": "user", "id": "ou_b", "name": "Delivery"}]
    groups = [{"kind": "group", "id": "oc_g", "name": "Delivery"}]
    picked, found = choose_target(users, groups, "Delivery")
    assert picked is None
    assert len(found) == 2


def test_owner_includes_roy_assignee():
    config = SimpleNamespace(
        lark_relay_owner_open_ids=["ou_cfg"],
        tech_support_assignees=[
            {"name": "Roy", "open_id": "ou_roy"},
            {"name": "Cisco-BE", "open_id": "ou_cisco"},
        ],
    )
    assert owner_open_ids(config) == {"ou_cfg", "ou_roy"}


def test_at_mention_sends_to_that_open_id():
    message = {
        "mentions": [
            {
                "key": "@_user_1",
                "id": {"open_id": "ou_brian"},
                "name": "Brian Wong",
            }
        ]
    }
    mentions = mention_users(message)
    picked, found = target_from_mentions("send to @_user_1".split("send to ", 1)[1], mentions)
    assert picked == {"kind": "user", "id": "ou_brian", "name": "Brian Wong"}
    assert len(found) == 1
    assert substitute_mentions("hi @_user_1", mentions) == "hi @Brian Wong"


def test_two_mentions_do_not_send():
    mentions = {
        "@_user_1": {"kind": "user", "id": "ou_a", "name": "Brian Wong"},
        "@_user_2": {"kind": "user", "id": "ou_b", "name": "Roy"},
    }
    picked, found = target_from_mentions("@_user_1 @_user_2", mentions)
    assert picked is None
    assert len(found) == 2


def test_claim_message_once():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["LARK_RELAY_SEEN"] = str(Path(tmp) / "seen.json")
        assert claim_message("om_1") is True
        assert claim_message("om_1") is False
        assert claim_message("om_2") is True
