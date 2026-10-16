import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from bot.workflow_form_claim import (
    assign_form_sender,
    begin_form_send,
    finish_form_send,
    form_send_status,
    live_form_speaker,
    pending_form_sends,
    reclaim_expired_form_sends,
    release_form_send,
    reserve_form_send,
)


def test_form_send_status_reads_claim(tmp_path: Path):
    path = tmp_path / "claim.json"
    assert form_send_status(path, "rec1") == ""
    reserve_form_send(
        path,
        "rec1",
        chat_id=-100,
        project_name="BotVault",
        requested_by="roy",
        now=1_000,
    )
    assert form_send_status(path, "rec1") == "reserved"
    assign_form_sender(path, "rec1", "josh", now=1_002)
    assert form_send_status(path, "rec1") == "assigned"
    finish_form_send(path, "rec1", "josh", now=1_020)
    assert form_send_status(path, "rec1") == "sent"


def test_speaker_is_the_other_bot_when_both_are_in_the_group():
    assert live_form_speaker("roy", peer_in_group=True) == "josh"
    assert live_form_speaker("josh", peer_in_group=True) == "roy"


def test_speaker_is_the_issuer_when_alone():
    assert live_form_speaker("roy", peer_in_group=False) == "roy"
    assert live_form_speaker("josh", peer_in_group=False) == "josh"


def test_speaker_is_the_other_bot_when_membership_is_unknown():
    assert live_form_speaker("roy", peer_in_group=None) == "josh"
    assert live_form_speaker("josh", peer_in_group=None) == "roy"


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


def _mark_live_cfg(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        workflow_mark_live_also_send_form=True,
        workflow_google_form_url="https://form.example",
        workflow_form_claim_state_file=str(tmp_path / "claim.json"),
        workflow_live_onboard_state_file=str(tmp_path / "onboard.json"),
        workflow_live_onboard_account="roy",
        group_replies_enabled=True,
    )


def test_unknown_peer_lookup_assigns_the_other_account(tmp_path, monkeypatch):
    from bot.workflow_mark_live import _prepare_mark_live_form_speaker

    async def unknown(*_args, **_kwargs):
        return None

    monkeypatch.setattr("bot.workflow_live_onboard.lookup_peer_in_chat", unknown)
    monkeypatch.setattr(
        "bot.workflow_live_onboard.load_peer_folder_titles",
        lambda: ({}, set(), set()),
    )
    speaker = asyncio.run(
        _prepare_mark_live_form_speaker(
            client=None,
            config=_mark_live_cfg(tmp_path),
            record_id="rec-unknown",
            project_name="Bot-DCA",
            chat_id=-5485534659,
            chat_title="Bot-DCA <> Botchain",
        )
    )
    assert speaker == "josh"
    claim = json.loads((tmp_path / "claim.json").read_text(encoding="utf-8"))
    assert claim["records"]["rec-unknown"]["owner"] == "josh"
    onboard = json.loads((tmp_path / "onboard.json").read_text(encoding="utf-8"))
    entry = onboard["projects"]["rec-unknown"]
    assert entry["roy_in"] is True
    assert "josh_in" not in entry


def test_confirmed_absent_peer_keeps_issuer_as_speaker(tmp_path, monkeypatch):
    from bot.workflow_mark_live import _prepare_mark_live_form_speaker

    async def absent(*_args, **_kwargs):
        return False

    monkeypatch.setattr("bot.workflow_live_onboard.lookup_peer_in_chat", absent)
    speaker = asyncio.run(
        _prepare_mark_live_form_speaker(
            client=None,
            config=_mark_live_cfg(tmp_path),
            record_id="rec-alone",
            project_name="Solo",
            chat_id=-1,
            chat_title="Solo <> Botchain",
        )
    )
    assert speaker == "roy"
    claim = json.loads((tmp_path / "claim.json").read_text(encoding="utf-8"))
    assert claim["records"]["rec-alone"]["owner"] == "roy"
