from __future__ import annotations

from bot.workflow_lark_recall import parse_recall_command, pick_recall_hits


def test_last_line_recall_uses_the_body():
    parsed = parse_recall_command(
        "本周（9/20–9/27）Botchain 生态项目方推特转发需求已汇总\nrecall"
    )
    assert parsed == ("本周（9/20–9/27）Botchain 生态项目方推特转发需求已汇总", True)


def test_inline_recall_and_plus():
    assert parse_recall_command("recall 本周（9/20–9/27）Botchain")[0] == "本周（9/20–9/27）Botchain"
    assert parse_recall_command("recall + 本周（9/20–9/27）Botchain")[0] == "本周（9/20–9/27）Botchain"
    parsed = parse_recall_command("ignore this\nrecall + 本周（9/20–9/27）Botchain")
    assert parsed[0] == "本周（9/20–9/27）Botchain"


def test_bare_recall_is_reply_only():
    assert parse_recall_command("recall") == ("", True)
    assert parse_recall_command("hello") is None
    assert parse_recall_command("send to Blake") is None


def test_unique_snippet_picks_one():
    items = [
        {"id": "om_1", "text": "本周（9/20–9/27）Botchain 生态项目方推特转发需求已汇总"},
        {"id": "om_2", "text": "【钱包地址】TipJar"},
    ]
    picked, hits = pick_recall_hits(items, "推特转发需求已汇总")
    assert picked["id"] == "om_1"
    assert len(hits) == 1


def test_ambiguous_snippets_do_not_pick():
    items = [
        {"id": "om_1", "text": "本周 Botchain 周报 A"},
        {"id": "om_2", "text": "本周 Botchain 周报 B"},
    ]
    picked, hits = pick_recall_hits(items, "本周 Botchain")
    assert picked is None
    assert len(hits) == 2
