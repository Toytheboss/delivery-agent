"""Learn new knowledge from Telegram messages containing the trigger word."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from typing import TYPE_CHECKING

from telethon.tl.custom.message import Message

if TYPE_CHECKING:
    from bot.config_loader import AppConfig
    from bot.knowledge import KnowledgeBase

logger = logging.getLogger(__name__)

_QUESTION_HINT_RE = re.compile(
    r"(？|\?|怎么|如何|怎样|什么|哪[里个些]|是否|能不能|可以吗|"
    r"how\b|what\b|where\b|which\b|why\b|can\b|does\b|is\b|are\b)",
    re.IGNORECASE,
)
_STOP_KW = frozenset(
    {
        "怎么",
        "如何",
        "怎样",
        "什么",
        "是否",
        "一个",
        "我们",
        "你们",
        "他们",
        "这个",
        "那个",
        "可以",
        "吗",
        "呢",
        "啊",
        "the",
        "and",
        "for",
        "with",
        "how",
        "what",
        "where",
        "which",
        "why",
        "can",
        "does",
        "is",
        "are",
        "you",
        "your",
    }
)


@dataclass
class LearnResult:
    success: bool
    message: str
    file_path: str | None = None


def in_learn_scope(
    chat_id: int,
    qa_tester: bool,
    in_qa_group: bool,
    in_botchain_folder: bool,
    config: AppConfig,
) -> bool:
    if not config.learn_enabled:
        return False
    if config.learn_scope_qa_groups and in_qa_group:
        return True
    if config.learn_scope_qa_testers and qa_tester:
        return True
    if config.learn_scope_botchain_folder and in_botchain_folder:
        return True
    return False


def contains_learn_trigger(text: str, trigger: str) -> bool:
    return trigger in (text or "")


def _inline_after_trigger(text: str, trigger: str) -> str:
    cleaned = re.sub(rf"^{re.escape(trigger)}[\s:：\-]*", "", (text or "").strip()).strip()
    if cleaned == trigger:
        return ""
    return cleaned


def extract_learn_content(
    message: Message,
    trigger: str,
    *,
    replied_text: str | None = None,
) -> str | None:
    """Extract content to save. Supports inline '学习 xxx' or reply with '学习'."""
    text = (message.raw_text or "").strip()
    if trigger not in text:
        return None

    if message.is_reply and replied_text is not None:
        replied_text = replied_text.strip()
        inline = _inline_after_trigger(text, trigger)
        if replied_text and not inline:
            return replied_text

    inline = re.split(rf"{re.escape(trigger)}[\s:：\-]*", text, maxsplit=1)
    if len(inline) > 1 and inline[1].strip():
        return inline[1].strip()

    cleaned = text.replace(trigger, "", 1).strip()
    return cleaned or None


def _looks_like_question(text: str) -> bool:
    t = (text or "").strip()
    # Partner questions can be long English checklists (addresses / ABIs / etc.)
    if not t or len(t) > 800:
        return False
    return bool(_QUESTION_HINT_RE.search(t))


def _split_embedded_qa(content: str) -> tuple[str | None, str]:
    """If absorb body is 'Question?\\n\\nAnswer…', peel the question off for indexing."""
    text = (content or "").strip()
    if not text:
        return None, text
    # First paragraph ending with ? / ？, rest is the answer
    m = re.match(
        r"^(.+?[?？])\s*\n\s*\n+(.+)$",
        text,
        re.DOTALL,
    )
    if not m:
        # Single newline after a short-ish question line
        m = re.match(
            r"^(.{12,800}?[?？])\s*\n+([A-Z\u4e00-\u9fff].+)$",
            text,
            re.DOTALL,
        )
    if not m:
        return None, text
    question = m.group(1).strip()
    answer = m.group(2).strip()
    if not _looks_like_question(question) or len(answer) < 20:
        return None, text
    # Avoid treating a mid-answer rhetorical '?' as the Q
    if question.count("\n") > 6:
        return None, text
    return question, answer


def _guess_keywords(question: str, answer: str, *, limit: int = 12) -> str:
    blob = f"{question}\n{answer[:400]}"
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"[a-zA-Z0-9_]{3,}|" r"[\u4e00-\u9fff]{2,8}", blob):
        t = raw.lower()
        if t in _STOP_KW or t in seen:
            continue
        seen.add(t)
        tokens.append(raw if not raw.isascii() else t)
        if len(tokens) >= limit:
            break
    return ", ".join(tokens)


def format_learned_body(
    content: str,
    *,
    related_question: str | None,
    meta: str,
    ts: str,
) -> str:
    """FAQ-shaped markdown so retrieval can score 【相关问题】 / keywords."""
    answer = content.strip()
    question = (related_question or "").strip()
    if question:
        keywords = _guess_keywords(question, answer)
        return (
            f"# 学习记录 {ts}\n\n"
            f"{meta}\n"
            f"【相关问题】{question}\n"
            f"【关键词】{keywords}\n"
            f"【参考回答-中文】{answer}\n"
        )
    # No question captured — still label the answer for fallback compose
    return (
        f"# 学习记录 {ts}\n\n"
        f"{meta}\n"
        f"【参考回答-中文】{answer}\n"
    )


def save_learned_content(
    content: str,
    knowledge_dir: Path,
    *,
    chat_id: int,
    sender_id: int | None,
    sender_username: str | None,
    subdirectory: str,
    related_question: str | None = None,
) -> Path:
    learned_dir = knowledge_dir / subdirectory
    learned_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"learned_{ts}.md"
    path = learned_dir / filename

    meta = (
        f"<!-- learned_at: {datetime.now().isoformat(timespec='seconds')} -->\n"
        f"<!-- chat_id: {chat_id} -->\n"
        f"<!-- sender_id: {sender_id} -->\n"
        f"<!-- sender: @{sender_username or 'unknown'} -->\n"
    )
    if related_question:
        meta += f"<!-- related_question: {related_question.replace('--', '- -')} -->\n"

    body = format_learned_body(
        content,
        related_question=related_question,
        meta=meta,
        ts=ts,
    )
    path.write_text(body, encoding="utf-8")
    return path


async def _resolve_related_question(
    message: Message,
    trigger: str,
    *,
    replied: Message | None,
    replied_text: str | None,
) -> str | None:
    """Best-effort: pair absorbed answer with the original user question."""
    text = (message.raw_text or "").strip()
    inline = _inline_after_trigger(text, trigger)

    # Case: reply to the question with `absorb <answer>`
    if replied_text and inline and _looks_like_question(replied_text):
        return replied_text.strip()

    # Case: reply to an answer with bare `absorb` — walk up one reply for the Q
    if replied is not None and replied.is_reply and not inline:
        parent = await replied.get_reply_message()
        if parent and (parent.raw_text or "").strip():
            parent_text = parent.raw_text.strip()
            if trigger not in parent_text and _looks_like_question(parent_text):
                return parent_text
            if trigger not in parent_text and len(parent_text) <= 120:
                return parent_text

    # Case: absorb message itself embeds "Q: ... / A: ..."
    m = re.search(
        r"(?:相关问题|问题|Q)\s*[:：]\s*(.+?)(?:\n|$)",
        inline or text,
        re.IGNORECASE,
    )
    if m:
        q = m.group(1).strip()
        if q:
            return q

    return None


async def handle_learn(
    message: Message,
    kb: KnowledgeBase,
    config: AppConfig,
    *,
    chat_id: int,
    sender_id: int | None,
    sender_username: str | None,
    owner_id: int | None = None,
) -> LearnResult:
    trigger = config.learn_trigger_word
    text = message.raw_text or ""

    if not contains_learn_trigger(text, trigger):
        return LearnResult(False, "no trigger")

    replied: Message | None = None
    replied_text: str | None = None
    if message.is_reply:
        replied = await message.get_reply_message()
        if replied:
            if owner_id is not None and replied.sender_id == owner_id:
                return LearnResult(False, "不能学习本账号发送的消息。")
            replied_text = replied.raw_text or ""

    content = extract_learn_content(message, trigger, replied_text=replied_text)
    if not content:
        return LearnResult(
            False,
            f"请在「{trigger}」后写上内容，或回复一条消息并发送「{trigger}」。",
        )

    if len(content) < config.learn_min_chars:
        return LearnResult(False, f"内容太短（至少 {config.learn_min_chars} 字）。")

    related_question = await _resolve_related_question(
        message,
        trigger,
        replied=replied,
        replied_text=replied_text,
    )

    # Absorb pasted as "Q?\n\nA…" without a reply-link — still index the Q.
    if not related_question:
        embedded_q, peeled = _split_embedded_qa(content)
        if embedded_q:
            related_question = embedded_q
            content = peeled

    try:
        path = save_learned_content(
            content,
            config.knowledge_dir,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_username=sender_username,
            subdirectory=config.learn_subdirectory,
            related_question=related_question,
        )
        count = kb.reload()
        logger.info(
            "Learned content saved to %s (%d chunks total, related_question=%r)",
            path,
            count,
            (related_question or "")[:80],
        )

        if getattr(config, "agent_kb_lark_sync_enabled", False):
            try:
                from bot.agent_kb_sync import sync_learned_file_to_lark
                from bot.metrics import inc as metrics_inc

                body = path.read_text(encoding="utf-8")
                record_id = sync_learned_file_to_lark(
                    path.name,
                    body,
                    app_token=getattr(config, "agent_kb_app_token", ""),
                    table_id=getattr(config, "agent_kb_table_id", ""),
                )
                if record_id:
                    metrics_inc("agent_kb_lark_sync_success")
            except Exception:  # noqa: BLE001
                logger.exception("Agent KB Lark sync failed for %s", path.name)

        try:
            from bot.metrics import inc as metrics_inc

            metrics_inc("absorb_learn_success")
        except Exception:  # noqa: BLE001
            pass

        preview = content[:80] + ("..." if len(content) > 80 else "")
        q_note = f"\n关联问题：{related_question[:60]}" if related_question else (
            "\n（未捕获到原问题；建议回复原问题后用 "
            f"「{trigger} 答案…」写入，检索会更准）"
        )
        return LearnResult(
            True,
            f"✅ 已加入知识库（共 {count} 条）{q_note}\n\n预览：{preview}",
            str(path),
        )
    except OSError as exc:
        logger.exception("Failed to save learned content")
        return LearnResult(False, f"保存失败：{exc}")
