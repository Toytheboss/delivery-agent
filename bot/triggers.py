"""Decide whether an incoming message should be processed."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon.tl.custom.message import Message

# Require a real question shape. Bare "Will do!" must NOT match via ^will\b.
QUESTION_MARKERS = re.compile(
    r"[\?？]"
    r"|^(what|how|where|when|why|who)\b"
    r"|^(can|could|would|should)\s+(i|we|you|he|she|it|they|this|that|someone|anyone)\b"
    r"|^(is|are|do|does|did|will)\s+(i|we|you|he|she|it|they|this|that|there|the|any|anyone)\b",
    re.IGNORECASE,
)

# Short acknowledgements / chitchat — never enter FAQ.
_ACK_RE = re.compile(
    r"^\s*("
    r"will do|got it|sounds good|makes sense|noted|lgtm|cool|sure|ok(?:ay)?|"
    r"thanks?(?:\s+you)?|thx|ty|np|no problem|all good|roger(?:\s+that)?|"
    r"好的|收到|明白|了解|嗯+|行|可以|没问题|谢谢|感谢|好勒|搞定"
    r")[\s!.。！~…]*$",
    re.IGNORECASE,
)

# Social greetings / post shares — casual emoji reply, not FAQ.
_SOCIAL_GREETING_RE = re.compile(
    r"^\s*("
    r"gm|gn|good\s*morning|good\s*evening|good\s*night|"
    r"hello|hiya|hey(?:\s+team)?|hi(?:\s+team)?|"
    r"早|早上好|晚安|大家好"
    r")[\s!.。！~…❤️☀️🙏👋🔥🚀✨😊]*$",
    re.IGNORECASE,
)
_X_LINK_RE = re.compile(
    r"https?://(?:(?:www|mobile)\.)?(?:x\.com|twitter\.com|t\.co)/\S+",
    re.IGNORECASE,
)
_SHARE_CAPTION_RE = re.compile(
    r"(made a post|just posted|posted (?:today|this)|check (?:this|it) out|"
    r"shared (?:a |our |my )?(?:post|tweet|update)|"
    r"发了|发帖|发了一条|分享一下|刚发)",
    re.IGNORECASE,
)
_QUESTIONISH_RE = re.compile(
    r"[\?？]"
    r"|\b(can|could|would|should|what|how|where|when|why|who|which|"
    r"align|clarify|confirm|please (?:share|advise))\b",
    re.IGNORECASE,
)

# @username / @channel style tokens (Telegram usernames)
_MENTION_TOKEN_RE = re.compile(r"@[\w\d_]{3,32}", re.IGNORECASE)
# leftover after stripping mentions: whitespace / punctuation only
_TRIVIAL_RE = re.compile(r"^[\s\W_]*$", re.UNICODE)

_SOCIAL_REPLIES_EN = (
    "gm! ☀️",
    "gm gm 👋",
    "Nice — thanks for posting! 🔥",
    "Love it, appreciate you sharing 🙌",
    "Awesome update 🚀",
    "Looks great, thanks for the shoutout! ✨",
    "Saw it — nice work! 🔥🙌",
    "gm! Just saw the post ☀️🚀",
)
_SOCIAL_REPLIES_ZH = (
    "早上好 ☀️",
    "收到，赞一个 🙌",
    "发得漂亮 🔥",
    "辛苦了，支持！🚀",
    "看到了，很棒 ✨",
    "好的，谢谢分享 🙏🔥",
)


def is_social_chitchat(text: str) -> bool:
    """True for gm/gn / short greetings / X-post shares (not real FAQ questions)."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > 420:
        return False
    without_mentions = _MENTION_TOKEN_RE.sub(" ", stripped)
    without_mentions = re.sub(r"\s+", " ", without_mentions).strip()
    if not without_mentions:
        return False
    if _SOCIAL_GREETING_RE.match(without_mentions):
        return True
    if not _X_LINK_RE.search(stripped):
        return False
    # Real asks mixed with a link → leave for FAQ / human
    if _QUESTIONISH_RE.search(stripped):
        return False
    caption = _X_LINK_RE.sub(" ", stripped)
    caption = _MENTION_TOKEN_RE.sub(" ", caption)
    caption = re.sub(r"\s+", " ", caption).strip()
    if len(caption) <= 100:
        return True
    if _SHARE_CAPTION_RE.search(stripped) and len(caption) <= 180:
        return True
    return False


def pick_social_reply(text: str, *, seed: int | None = None) -> str:
    """Short casual reply with emoji; language follows the message loosely."""
    import random

    cjk = sum(1 for c in (text or "") if "\u4e00" <= c <= "\u9fff")
    pool = _SOCIAL_REPLIES_ZH if cjk >= 2 else _SOCIAL_REPLIES_EN
    rng = random.Random(seed)
    return rng.choice(pool)


def is_qa_tester(
    sender_id: int | None,
    username: str | None,
    qa_user_ids: set[int],
    qa_usernames: set[str],
) -> bool:
    if sender_id is not None and sender_id in qa_user_ids:
        return True
    if username and username.lower().lstrip("@") in qa_usernames:
        return True
    return False


def is_whitelisted(
    sender_id: int | None,
    username: str | None,
    ignore_user_ids: set[int],
    ignore_usernames: set[str],
) -> bool:
    if sender_id is not None and sender_id in ignore_user_ids:
        return True
    if username and username.lower().lstrip("@") in ignore_usernames:
        return True
    return False


def is_workflow_operator(
    sender_id: int | None,
    username: str | None,
    operator_user_ids: set[int],
    operator_usernames: set[str],
) -> bool:
    """Users allowed to trigger mark-live / send-form in project groups."""
    if sender_id is not None and sender_id in operator_user_ids:
        return True
    if username and username.lower().lstrip("@") in operator_usernames:
        return True
    return False


def mentions_me(message: Message, my_id: int, my_username: str | None) -> bool:
    if getattr(message, "mentioned", False):
        return True

    text = message.raw_text or ""
    if my_username and f"@{my_username.lower()}" in text.lower():
        return True

    for entity in message.entities or []:
        type_name = entity.__class__.__name__
        if type_name == "MessageEntityMentionName":
            offset = entity.offset
            length = entity.length
            segment = text[offset : offset + length]
            if my_username and segment.lower().lstrip("@") == my_username.lower():
                return True
        user_id = getattr(entity, "user_id", None)
        if user_id == my_id:
            return True

    if message.is_reply:
        reply = message.reply_to
        if reply and getattr(reply, "sender_id", None) == my_id:
            return True

    return False


def is_ack_or_chitchat(text: str) -> bool:
    """True for short acknowledgements that must not trigger FAQ."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    # Strip leading @mentions then re-check
    without = _MENTION_TOKEN_RE.sub(" ", stripped)
    without = re.sub(r"\s+", " ", without).strip()
    if not without:
        return True
    return bool(_ACK_RE.match(without))


def looks_like_question(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) < 8:
        return False
    if is_ack_or_chitchat(stripped):
        return False
    if QUESTION_MARKERS.search(stripped):
        return True
    # Chinese question patterns
    if any(p in stripped for p in ("吗", "么", "怎么", "如何", "什么", "哪", "是否", "能不能", "可不可以")):
        return True
    return False


def has_hint_keyword(text: str, keywords: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(k in lowered for k in keywords)


def is_mention_only(text: str) -> bool:
    """True when message is only @mentions (no real question / content).

    Prevents bare ``@Roy4by4`` from entering FAQ + query-rewrite.
    """
    stripped = (text or "").strip()
    if not stripped:
        return True
    without = _MENTION_TOKEN_RE.sub(" ", stripped)
    without = re.sub(r"\s+", " ", without).strip()
    if not without:
        return True
    return bool(_TRIVIAL_RE.match(without))


def should_process(
    message: Message,
    my_id: int,
    my_username: str | None,
    hint_keywords: list[str],
    require_mention_or_question: bool,
    qa_tester: bool = False,
) -> bool:
    text = message.raw_text or ""
    if not text.strip():
        return False

    # Bare @mention / empty ping: never FAQ-reply (incl. QA testers)
    if is_mention_only(text):
        return False

    # "Will do!" / "收到" etc. — never FAQ, even for QA testers or @mentions
    if is_ack_or_chitchat(text):
        return False

    # QA 测试号：在 Delivery 群内任意提问即可触发，无需 @ 主号
    if qa_tester:
        return True

    mentioned = mentions_me(message, my_id, my_username)
    question = looks_like_question(text)
    hinted = has_hint_keyword(text, hint_keywords)

    if not require_mention_or_question:
        return True

    return mentioned or question or hinted
