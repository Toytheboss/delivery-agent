"""Automation scope follows group membership, not Telegram folder placement."""

from bot.folder_scope import chat_in_joined_scope


def test_live_group_is_in_scope() -> None:
    assert chat_in_joined_scope(
        1, is_group=True, deactivated=False, broadcast_only=False, ignored=set()
    )


def test_ignored_deactivated_broadcast_and_private_are_out() -> None:
    assert not chat_in_joined_scope(
        1, is_group=True, deactivated=False, broadcast_only=False, ignored={1}
    )
    assert not chat_in_joined_scope(
        2, is_group=True, deactivated=True, broadcast_only=False, ignored=set()
    )
    assert not chat_in_joined_scope(
        3, is_group=True, deactivated=False, broadcast_only=True, ignored=set()
    )
    assert not chat_in_joined_scope(
        4, is_group=False, deactivated=False, broadcast_only=False, ignored=set()
    )
