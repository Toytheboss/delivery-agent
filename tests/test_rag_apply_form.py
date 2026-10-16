from bot.knowledge import Chunk, SearchHit
from bot.rag import (
    _append_missing_links,
    _question_wants_apply_form,
    _scrub_blocked_urls,
    _urls_for_reply,
)

APPLY = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSfbzPvwMlXbKWZUm2N1Dyg8hXXGwU4LKUFFpJX04LP8lbMPQA/viewform"
)
DOCS = "https://www.botchain.ai/zh/project-party"


def _hit() -> SearchHit:
    text = (
        "官网上有生态页：" + DOCS + "\n"
        "想进生态的话可以走申请表：\n" + APPLY + "\n"
        "【来源】" + DOCS
    )
    return SearchHit(chunk=Chunk(source="kb.md", text=text, tokens=set()), score=0.9)


def test_apply_intent_is_tight():
    assert _question_wants_apply_form("怎么申请 Plan A")
    assert _question_wants_apply_form("How do I apply for ecosystem support?")
    assert not _question_wants_apply_form("BOT Chain 生态有多少项目")
    assert not _question_wants_apply_form("What is Money on BOT Chain?")


def test_backfill_skips_apply_form_unless_asked():
    hits = [_hit()]
    filled = _append_missing_links("生态大概六百多个项目。", hits, question="生态有多少项目")
    assert APPLY not in filled
    assert DOCS in filled
    apply_q = _urls_for_reply(hits, question="怎么申请扶持")
    assert APPLY in apply_q


def test_scrub_strips_apply_form_from_casual_answers():
    raw = f"生态页在这里 {DOCS}\n{APPLY}"
    cleaned = _scrub_blocked_urls(raw, question="生态有多少项目")
    assert APPLY not in cleaned
    assert DOCS in cleaned
    kept = _scrub_blocked_urls(raw, question="怎么申请 Plan B")
    assert APPLY in kept
