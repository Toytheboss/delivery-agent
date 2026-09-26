from pathlib import Path

from bot.workflow_form_claim import (
    assign_form_sender,
    begin_form_send,
    finish_form_send,
    live_form_speaker,
    pending_form_sends,
    reclaim_expired_form_sends,
    release_form_send,
    reserve_form_send,
)


def test_speaker_is_the_other_bot_when_both_are_in_the_group():
    assert live_form_speaker("roy", peer_in_group=True) == "josh"
    assert live_form_speaker("josh", peer_in_group=True) == "roy"


def test_speaker_is_the_issuer_when_alone():
    assert live_form_speaker("roy", peer_in_group=False) == "roy"
    assert live_form_speaker("josh", peer_in_group=False) == "josh"


def test_reserve_blocks_both_senders_until_assigned(tmp_path: Path):
    path = tmp_path / "claim.json"
    reserve_form_send(
        path,
        "rec1",
        chat_id=-100,
        project_name="BotVault",
        requested_by="roy",
        now=1_000,
    )
    assert begin_form_send(path, "rec1", "roy", now=1_001) == "wait"
    assert begin_form_send(path, "rec1", "josh", now=1_001) == "wait"
    assert (
        assign_form_sender(
            path,
            "rec1",
            "josh",
            chat_id=-100,
            project_name="BotVault",
            requested_by="roy",
            now=1_002,
        )
        == "josh"
    )
    assert begin_form_send(path, "rec1", "roy", now=1_003) == "wait"
    assert begin_form_send(path, "rec1", "josh", now=1_003) == "send"
    assert begin_form_send(path, "rec1", "roy", now=1_004) == "wait"
    finish_form_send(path, "rec1", "josh", now=1_020)
    assert begin_form_send(path, "rec1", "roy", now=1_021) == "done"
    assert begin_form_send(path, "rec1", "josh", now=1_021) == "done"


def test_first_unassigned_sender_wins(tmp_path: Path):
    path = tmp_path / "claim.json"
    assert begin_form_send(path, "rec2", "roy", chat_id=-5, now=10) == "send"
    assert begin_form_send(path, "rec2", "josh", chat_id=-5, now=11) == "wait"
    release_form_send(path, "rec2", "roy", now=12)
    assert pending_form_sends(path, "roy")[0]["record_id"] == "rec2"
    assert begin_form_send(path, "rec2", "roy", now=13) == "send"


def test_expired_handoff_returns_to_the_issuer(tmp_path: Path):
    path = tmp_path / "claim.json"
    assign_form_sender(
        path,
        "rec3",
        "josh",
        chat_id=-7,
        project_name="BotVault",
        requested_by="roy",
        now=100,
    )
    assert reclaim_expired_form_sends(path, "roy", now=140) == []
    jobs = reclaim_expired_form_sends(path, "roy", now=146)
    assert [job["record_id"] for job in jobs] == ["rec3"]
    assert jobs[0]["owner"] == "roy"
    assert begin_form_send(path, "rec3", "josh", now=147) == "wait"
    assert begin_form_send(path, "rec3", "roy", now=147) == "send"
