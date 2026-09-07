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
    r"yup|yeah|yes|done|perfect|awesome|great|"
    r"好的|收到|明白|了解|嗯+|行|可以|没问题|谢谢|感谢|好勒|搞定"
    r")[\s!.。！~…👍✅🙏]*$",
    re.IGNORECASE,
)

_SOFT_CLOSE_ACK_RE = re.compile(
    r"(?is)^(?:"
    r"(?:all\s+)?done(?:\s+here)?|"
    r"appreciate(?:\s+the)?\s+patience|"
    r"thanks?\s+for\s+(?:the\s+)?patience|"
    r"thanks?\s+for\s+(?:your\s+)?help|"
    r"thanks?\s+for\s+(?:the\s+)?support|"
    r"感谢耐心|辛苦了|搞定了|弄好了|处理好了"
    r")"
    r"(?:[\s,.，。!！~…👍🙏]*"
    r"(?:all\s+done|appreciate(?:\s+the)?\s+patience|"
    r"thanks?\s+for\s+(?:the\s+)?patience|"
    r"感谢耐心|辛苦了|搞定了)?"
    r"[\s,.，。!！~…👍🙏]*)*$"
)


_SOCIAL_GREETING_RE = re.compile(
    r"^\s*("
    r"gm|gn|good\s*morning|good\s*evening|good\s*night|"
    r"hello|hiya|hey(?:\s+team)?|hi(?:\s+team)?|"
    r"早|早上好|晚安|大家好"
    r")[\s!.。！~…❤️☀️🙏👋🔥🚀✨😊]*$",
    re.IGNORECASE,
)

_SOCIAL_GREETING_LOOSE_RE = re.compile(
    r"^\s*("
    r"gm|gn|good\s*morning|good\s*evening|good\s*night|"
    r"hello|hiya|hey|hi|"
    r"早|早上好|晚安|大家好"
    r")"
    r"(?:\s+[@\w][\w.\-]*){0,4}"
    r"[\s!.。！~…❤️☀️🙏👋🔥🚀✨😊]*$",
    re.IGNORECASE,
)

_ACK_LOOSE_RE = re.compile(
    r"^\s*("
    r"(?:yup|yeah|yes|yep|ok(?:ay)?|noted|done|cool|sure|perfect|awesome|great|"
    r"will do|got it|sounds good|all good|lgtm|"
    r"thanks?(?:\s+you)?|thx|ty|"
    r"好的|收到|明白|了解|谢谢|感谢|搞定)"
    r")"
    r"(?:"
    r"[\s,，.。!！~…👍✅🙏😅❤️]*|"
    r"\s+(?:already\s+done|done|submitted|all|everyone|guys|team|alot|a\s+lot|"
    r"allow\s+us\s+little\s+time|little\s+time|for\s+now|too|then|boss|"
    r"everything\s+is\s+fine|i(?:['’]?m)?\s*(?:good|in)|"
    r"not\s+yet|will\s+do|got\s+it|"
    r"大家|各位|啦|哦|呀|哈)"
    r"){0,6}$",
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
    r"align|clarify|confirm|please (?:share|advise|help|check|fill)|"
    r"any\s+(?:update|word|news|feedback)|update\s+on)\b"
    r"|吗|怎么|如何|什么|是否|能不能|可不可以",
    re.IGNORECASE,
)

_BUILDERS_WELCOME_RE = re.compile(
    r"welcome\s+to\s+bot\s*chain\s+builders\s+hub",
    re.IGNORECASE,
)

_FORM_BLAST_RE = re.compile(
    r"(forms\.gle/|docs\.google\.com/forms/|"
    r"congrats!.{0,80}live\s+on\s+bot\s*chain|"
    r"follow-?up\s+onboarding|"
    r"friendly\s+reminder.{0,60}onboarding\s+form)",
    re.IGNORECASE | re.DOTALL,
)

_TECH_HINT_RE = re.compile(
    r"\b(deploy|mainnet|testnet|contract|rpc|chainid|gas|wallet|token|"
    r"bridge|sdk|api|abi|solidity|audit|grant|proposal|pr\b|debug|node|"
    r"合约|主网|测试网|部署|钱包|节点)\b",
    re.IGNORECASE,
)

_MENTION_TOKEN_RE = re.compile(r"@[\w\d_]{3,32}", re.IGNORECASE)
_TRIVIAL_RE = re.compile(r"^[\s\W_]*$", re.UNICODE)

_SOCIAL_REPLIES_EN = (
    "Hey! Good to see you 👋",
    "gm — hope your day's going well ☀️",
    "Hi there! Nice to hear from you 🙌",
    "Hey hey 👋 how's it going?",
    "gm gm! ☀️",
    "Hello! Hope you're doing well ✨",
)

_SOCIAL_REPLIES_ZH = (
    "你好呀 👋",
    "早上好，今天顺利吗 ☀️",
    "嗨，看到你了 🙌",
    "你好～有事随时说 ✨",
    "早 ☀️",
    "在的，你好 👋",
)

_SHARE_REPLIES_EN = (
    "Nice — thanks for sharing! 🔥",
    "Love it, appreciate you posting 🙌",
    "Awesome update 🚀",
    "Looks great, thanks for the shoutout! ✨",
    "Saw it — nice work! 🔥🙌",
)

_SHARE_REPLIES_ZH = (
    "收到，赞一个 🙌",
    "发得漂亮 🔥",
    "辛苦了，支持！🚀",
    "看到了，很棒 ✨",
    "好的，谢谢分享 🙏🔥",
)

_ACK_REPLIES_EN = (
    "Got it, thanks! 👍",
    "Appreciate the update 🙌",
    "Nice, noted!",
    "Perfect, thanks 👌",
    "Cool — thanks for letting me know 👍",
    "Sounds good!",
    "Alright, thanks! ✨",
)

_ACK_REPLIES_ZH = (
    "收到，谢谢 👍",
    "好的，了解了 🙌",
    "嗯嗯，记下了",
    "辛苦了 👌",
    "好嘞～",
    "没问题 🙌",
    "收到～有进展再喊我",
)
_CLOSE_ACK_REPLIES_EN = (
    "All good — thanks for hanging in there.",
    "Appreciate it on our side too.",
    "Nice, thanks for the patience.",
    "Perfect — glad we got there.",
)
_CLOSE_ACK_REPLIES_ZH = (
    "好的，也谢谢耐心。",
    "搞定就好，有事再说。",
    "收到，辛苦了。",
)



def _strip_mentions(text: str) -> str:
    without = _MENTION_TOKEN_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", without).strip()


def is_builders_welcome_blast(text: str) -> bool:
    """Community welcome template — ignore for FAQ and human-review."""
    return bool(_BUILDERS_WELCOME_RE.search(text or ""))


def is_outbound_form_blast(text: str) -> bool:
    """Congrats / Google Form onboarding copy — not a project question."""
    return bool(_FORM_BLAST_RE.search(text or ""))



_URL_ONLY_RE = re.compile(
    r"https?://[^\s<>\"']+|wss://[^\s<>\"']+",
    re.IGNORECASE,
)


def is_link_only_share(text: str) -> bool:
    """True when the message is essentially just URL(s), not a FAQ question."""
    stripped = (text or "").strip()
    if not stripped or not _URL_ONLY_RE.search(stripped):
        return False
    remainder = _URL_ONLY_RE.sub(" ", stripped)
    remainder = _MENTION_TOKEN_RE.sub(" ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip()
    if not remainder:
        return True
    if len(remainder) <= 24 and not re.search(r"[\?？]", remainder):
        if re.match(
            r"(?is)^(check(?:\s+this)?|see(?:\s+this)?|here|link|看看|这个|这个链接|分享一下)?[\s!.。！~…]*$",
            remainder,
        ):
            return True
    return False


def is_social_chitchat(text: str) -> bool:
    """True for gm/gn / short greetings / X-post shares (not real FAQ questions)."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > 420:
        return False
    if is_builders_welcome_blast(stripped) or is_outbound_form_blast(stripped):
        return False
    without_mentions = _strip_mentions(stripped)
    if not without_mentions:
        return False
    if re.search(r"[\?？]", without_mentions):
        return False
    if _QUESTIONISH_RE.search(without_mentions):
        # Allow pure/loose greeting only when no strong ask body.
        if not (
            _SOCIAL_GREETING_RE.match(without_mentions)
            or (
                len(without_mentions) <= 48
                and _SOCIAL_GREETING_LOOSE_RE.match(without_mentions)
            )
        ):
            return False
    if _SOCIAL_GREETING_RE.match(without_mentions):
        return True
    if len(without_mentions) <= 64 and _SOCIAL_GREETING_LOOSE_RE.match(without_mentions):
        if not _TECH_HINT_RE.search(without_mentions):
            return True
    if not _X_LINK_RE.search(stripped):
        return False
    if _QUESTIONISH_RE.search(stripped):
        return False
    caption = _strip_mentions(_X_LINK_RE.sub(" ", stripped))
    if len(caption) <= 100:
        return True
    if _SHARE_CAPTION_RE.search(stripped) and len(caption) <= 180:
        return True
    return False


def pick_social_reply(text: str, *, seed: int | None = None) -> str:
    """Warm greeting or share reply; language follows the message loosely."""
    import random

    cjk = sum(1 for c in (text or "") if "\u4e00" <= c <= "\u9fff")
    if _X_LINK_RE.search(text or ""):
        pool = _SHARE_REPLIES_ZH if cjk >= 2 else _SHARE_REPLIES_EN
    else:
        pool = _SOCIAL_REPLIES_ZH if cjk >= 2 else _SOCIAL_REPLIES_EN
    rng = random.Random(seed)
    return rng.choice(pool)


def pick_ack_reply(text: str, *, seed: int | None = None) -> str:
    """Warm acknowledgement reply; not FAQ / not knowledge-based."""
    import random

    cjk = sum(1 for c in (text or "") if "一" <= c <= "鿿")
    without = _MENTION_TOKEN_RE.sub(" ", text or "")
    without = re.sub(r"\s+", " ", without).strip()
    soft_close = bool(without and _SOFT_CLOSE_ACK_RE.match(without))
    if soft_close:
        pool = _CLOSE_ACK_REPLIES_ZH if cjk >= 1 else _CLOSE_ACK_REPLIES_EN
    else:
        pool = _ACK_REPLIES_ZH if cjk >= 1 else _ACK_REPLIES_EN
    rng = random.Random(seed)
    return rng.choice(pool)

def pick_casual_reply(text: str, *, seed: int | None = None) -> str:
    """Social greeting/share → social pool; short ack → ack pool."""
    if is_social_chitchat(text):
        return pick_social_reply(text, seed=seed)
    return pick_ack_reply(text, seed=seed)


def is_casual_message(text: str) -> bool:
    """Greeting, share, or short ack — safe for warm casual auto-reply."""
    return is_social_chitchat(text) or is_ack_or_chitchat(text)



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
    if explicitly_mentions_me(message, my_id, my_username):
        return True

    if message.is_reply:
        reply = message.reply_to
        if reply and getattr(reply, "sender_id", None) == my_id:
            return True

    return False


def explicitly_mentions_me(
    message: Message, my_id: int, my_username: str | None
) -> bool:
    """True only for an explicit @username / mention entity, not a reply."""
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

    return False


def is_ack_or_chitchat(text: str) -> bool:
    """True for short acknowledgements that must not trigger FAQ."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    if is_builders_welcome_blast(stripped) or is_outbound_form_blast(stripped):
        return False
    without = _strip_mentions(stripped)
    if not without:
        # Bare @mention ping (e.g. @all) is not an acknowledgement.
        return False
    if re.search(r"[\?？]", without) or _TECH_HINT_RE.search(without):
        return False
    if _QUESTIONISH_RE.search(without) and not re.match(
        r"(?is)^(thanks?|thx|ty|noted|ok(?:ay)?|yup|yeah|yes)\b", without
    ):
        return False
    if _ACK_RE.match(without):
        return True
    if len(without) <= 80 and _ACK_LOOSE_RE.match(without):
        return True
    if len(without) <= 48 and re.match(
        r"(?is)^(that was quick|its approved|it'?s approved|check your dm|"
        r"oh!?\s*noted|noted\b.*little time|noted\b.*thanks|"
        r"i know[,.]?\s*i was just telling you|"
        r"yes[,.]?\s*everything is fine|"
        r"not yet.*(?:thx|thanks)|"
        r"done(?:\s+submitted)?|"
        r"appreciate(?:\s+it)?)"
        r"[\s!.。！~…👍✅🙏😅😂❤️]*$",
        without,
    ):
        return True
    # Closing soft-acks: all done / appreciate the patience
    if len(without) <= 120 and _SOFT_CLOSE_ACK_RE.match(without):
        return True

    return False


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

    Prevents bare ``@Josh_0zh`` from entering FAQ + query-rewrite.
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

    # URL-only shares: never FAQ
    if is_link_only_share(text):
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
