from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from bot.workflow_project_info_submit import (
    format_submit_reply,
    is_project_info_submit,
    maybe_handle_project_info_submit,
    message_text,
    parse_submit_payload,
    progress_coord_is_final_failed,
    project_name_from_quoted,
    quoted_result_is_kpi_failed,
    upsert_wallet_row,
    write_pr_link,
)


def test_command_accepts_first_line_only():
    assert is_project_info_submit("Project info submit")
    assert is_project_info_submit("/Project info submit\nhttps://x.com/Foo")
    assert is_project_info_submit("@_user_1 Project info submit")
    assert not is_project_info_submit("please Project info submit")
    assert not is_project_info_submit("pr support")


def test_status_url_is_pr_not_profile():
    contract, twitter, pr = parse_submit_payload(
        "https://x.com/OfficialHandle\n"
        "0x9a76DD1cf04C9142A8939a9b124f738e621BE249\n"
        "https://x.com/OfficialHandle/status/1234567890?s=20"
    )
    assert contract == "0x9a76dd1cf04c9142a8939a9b124f738e621be249"
    assert twitter == "https://x.com/OfficialHandle"
    assert pr == "https://x.com/OfficialHandle/status/1234567890"


def test_tweet_alone_does_not_fill_twitter():
    contract, twitter, pr = parse_submit_payload(
        "https://x.com/Foo/status/9"
    )
    assert contract == ""
    assert twitter == ""
    assert pr == "https://x.com/Foo/status/9"
    _, mention, _ = parse_submit_payload("thanks @Daniel")
    assert mention == ""


def test_two_contracts_are_both_kept():
    first = "0x" + ("ab" * 20)
    second = "0x" + ("cd" * 20)
    tx = "0x" + ("ef" * 32)
    contract, twitter, pr = parse_submit_payload(
        f"0x{'CD' * 20}\n{tx}\n{first}\n{first}"
    )
    assert contract == f"{second}\n{first}"
    assert twitter == ""
    assert pr == ""
    text = format_submit_reply(
        project="Relay",
        wallet={"action": "updated", "contract": contract, "record_ids": ["rec"]},
    )
    assert f"Contract: {second}" in text
    assert f"Contract: {first}" in text


def test_transaction_hash_is_not_a_contract():
    tx = "0x" + ("ab" * 32)
    contract, twitter, pr = parse_submit_payload(tx)
    assert contract == ""
    assert twitter == ""
    assert pr == ""
    address = "0x" + ("cd" * 20)
    contract, _, _ = parse_submit_payload(f"contract {address}")
    assert contract == address


def test_markdown_post_body_keeps_project_line():
    import json

    body = {
        "msg_type": "post",
        "body": {
            "content": json.dumps(
                {
                    "content": [
                        [
                            {
                                "tag": "md",
                                "text": (
                                    '<at user_id="ou_1"></at>\n\n'
                                    "**Project:** `doubledouble`\n"
                                    "**BD:** Daniel"
                                ),
                            }
                        ]
                    ]
                }
            )
        },
    }
    assert project_name_from_quoted(message_text(body)) == "doubledouble"


def test_project_name_from_result_post():
    text = (
        '<at user_id="ou_1"></at>\n\n'
        "**Project:** `onchainpolls.xyz`\n"
        "**Result:** Held for rectification"
    )
    assert project_name_from_quoted(text) == "onchainpolls.xyz"
    assert project_name_from_quoted("hello") == ""


def test_wallet_create_and_duplicate_update():
    config = SimpleNamespace(
        workflow_base_app_token="app",
        workflow_wallet_table_id="tbl",
        workflow_wallet_name_field="Project name",
    )
    created: list[dict] = []
    updated: list[tuple[str, dict]] = []

    def fake_create(_token, _app, _tbl, fields):
        created.append(fields)
        return "rec_new"

    def fake_update(_token, _app, _tbl, rid, fields):
        updated.append((rid, fields))

    with patch("bot.workflow_project_info_submit.create_record", fake_create), patch(
        "bot.workflow_project_info_submit.update_record", fake_update
    ):
        made = upsert_wallet_row(
            "tok",
            config,
            project_name="Relay",
            contract="0xabc",
            twitter="https://x.com/Foo",
            rows=[],
        )
        assert made["action"] == "created"
        assert created[0]["Project name"] == "Relay"
        skipped = upsert_wallet_row(
            "tok",
            config,
            project_name="Relay",
            contract="",
            twitter="",
            rows=[],
        )
        assert skipped["action"] == "skipped"
        assert len(created) == 1
        dup = upsert_wallet_row(
            "tok",
            config,
            project_name="onchainpolls",
            contract="0xabc",
            twitter="https://x.com/Foo",
            rows=[
                {"record_id": "rec1", "fields": {"Project name": "Onchainpolls"}},
                {"record_id": "rec2", "fields": {"Project name": "OnChain Polls"}},
            ],
        )
        assert dup["duplicate_rows"] is True
        assert {rid for rid, _fields in updated} == {"rec1", "rec2"}


def test_pr_writes_kpi2_and_does_not_create_progress_row():
    config = SimpleNamespace(
        workflow_base_app_token="app",
        workflow_progress_table_id="tblp",
        workflow_project_name_field="项目名称 Project Name",
        pr_capture_link_field="KPI 2 - PR 新闻链接验证",
    )
    updated: list[tuple[str, dict]] = []

    def fake_update(_token, _app, _tbl, rid, fields):
        updated.append((rid, fields))

    with patch("bot.workflow_project_info_submit.update_record", fake_update), patch(
        "bot.workflow_project_info_submit.create_record"
    ) as create:
        missing = write_pr_link(
            "tok",
            config,
            project_name="Relay",
            pr_url="https://x.com/a/status/1",
            rows=[],
        )
        assert missing["reason"] == "progress_missing"
        create.assert_not_called()
        found = write_pr_link(
            "tok",
            config,
            project_name="Relay",
            pr_url="https://x.com/a/status/1",
            rows=[
                {
                    "record_id": "recp",
                    "fields": {
                        "项目名称 Project Name": "Relay",
                        "主网上线时间": "2026-09-10T00:00:00+08:00",
                    },
                }
            ],
        )
        assert found["action"] == "updated"
        assert updated[0][1]["KPI 2 - PR 新闻链接验证"] == "https://x.com/a/status/1"
        assert updated[0][1]["新闻验证结果"] == "通过"


def test_reply_copy():
    assert "Reply to the project result post" in format_submit_reply(
        project="", reason="no_quote"
    )
    text = format_submit_reply(
        project="Relay",
        wallet={
            "action": "created",
            "twitter": "https://x.com/a",
            "contract": "0x1",
            "record_ids": ["rec"],
        },
        pr={"ok": True, "action": "updated", "pr": "https://x.com/a/status/1", "record_ids": ["p"]},
    )
    assert "Created info form row for Relay." in text
    assert "PR written to KPI 2." in text
    held = format_submit_reply(
        project="Relay",
        pr={"ok": False, "reason": "progress_missing"},
    )
    assert "no progress row" in held
    failed = format_submit_reply(project="Relay", reason="final_failed")
    assert "Second check already failed for this project." in failed
    assert "该项目二审已不通过，无法再次补交或审核。" in failed


def test_quoted_result_detects_kpi_failed():
    assert quoted_result_is_kpi_failed(
        "**Result:** `KPI failed`\n**Summary:** done"
    )
    assert quoted_result_is_kpi_failed("Result: KPI failed")
    assert not quoted_result_is_kpi_failed("Result: Valid KPI")
    assert not quoted_result_is_kpi_failed("Result: Held for rectification")


def test_progress_coord_final_failed_uses_table():
    config = SimpleNamespace(
        workflow_base_app_token="app",
        workflow_progress_table_id="tbl",
        workflow_project_name_field="项目名称 Project Name",
    )
    rows = [
        {
            "record_id": "rec1",
            "fields": {
                "项目名称 Project Name": "Relay",
                "主网上线时间": "2026-09-10T00:00:00+08:00",
                "KPI 统筹": "不通过",
            },
        }
    ]
    with patch(
        "bot.workflow_project_info_submit.list_records",
        return_value=rows,
    ):
        assert progress_coord_is_final_failed(
            "tok", config, project_name="Relay", quoted=""
        )


def test_progress_coord_held_is_not_final_failed():
    config = SimpleNamespace(
        workflow_base_app_token="app",
        workflow_progress_table_id="tbl",
        workflow_project_name_field="项目名称 Project Name",
    )
    rows = [
        {
            "record_id": "rec1",
            "fields": {
                "项目名称 Project Name": "Relay",
                "主网上线时间": "2026-09-10T00:00:00+08:00",
                "KPI 统筹": "暂扣整改",
            },
        }
    ]
    with patch(
        "bot.workflow_project_info_submit.list_records",
        return_value=rows,
    ):
        assert not progress_coord_is_final_failed(
            "tok",
            config,
            project_name="Relay",
            quoted="Result: KPI failed",
        )


def test_submit_rejects_final_failed_without_write():
    config = SimpleNamespace(
        raw={},
        workflow_live_onboard_lark_chat_id="oc_verify",
        workflow_base_app_token="app",
        workflow_progress_table_id="tbl",
        workflow_project_name_field="项目名称 Project Name",
    )
    event = {
        "sender": {"sender_type": "user"},
        "message": {
            "chat_id": "oc_verify",
            "message_id": "om_1",
            "parent_id": "om_parent",
            "message_type": "text",
            "content": '{"text":"https://x.com/foo"}',
        },
    }
    parent = {
        "message_type": "post",
        "body": {
            "content": (
                '{"content":[[{"tag":"md","text":'
                '"**Project:** `Relay`\\n**Result:** KPI failed"}]]}'
            )
        },
    }
    replies: list[str] = []
    with patch(
        "bot.workflow_kpi_write.kpi_checks_on_this_host", lambda: True
    ), patch(
        "bot.workflow_project_info_submit.claim_message",
        return_value=True,
    ), patch(
        "bot.workflow_project_info_submit._lark_creds",
        return_value=("id", "secret"),
    ), patch(
        "bot.workflow_project_info_submit.get_tenant_access_token",
        return_value="tok",
    ), patch(
        "bot.workflow_lark_recall.get_message",
        return_value=parent,
    ), patch(
        "bot.workflow_project_info_submit.progress_coord_is_final_failed",
        return_value=True,
    ), patch(
        "bot.workflow_project_info_submit.upsert_wallet_row"
    ) as wallet, patch(
        "bot.workflow_project_info_submit.write_pr_link"
    ) as pr, patch(
        "bot.workflow_project_info_submit._reply",
        side_effect=lambda _t, _m, text: replies.append(text),
    ):
        out = maybe_handle_project_info_submit(config, event)
    assert out and out.get("project_info_submit") == "final_failed"
    assert wallet.call_count == 0
    assert pr.call_count == 0
    assert "Second check already failed" in replies[0]
    assert "该项目二审已不通过" in replies[0]


def test_submit_ignored_on_delivery_host():
    config = SimpleNamespace(
        raw={},
        workflow_live_onboard_lark_chat_id="oc_verify",
    )
    event = {
        "sender": {"sender_type": "user"},
        "message": {
            "chat_id": "oc_verify",
            "message_id": "om_1",
            "parent_id": "om_parent",
            "message_type": "text",
            "content": '{"text":"0x' + ("ab" * 20) + '"}',
        },
    }
    with patch(
        "bot.workflow_kpi_write.kpi_checks_on_this_host",
        lambda: False,
    ):
        assert maybe_handle_project_info_submit(config, event) is None
