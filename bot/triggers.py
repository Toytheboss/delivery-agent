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
    r"will do|got it|sounds good|makes sense|noted(?:\s+\w+)?|lgtm|cool|sure+|ok(?:ay|ey|ok)?|"
    r"thanks?(?:\s+you)?|thx|ty|np|no problem|all good|roger(?:\s+that)?|"
    r"alright|awesome|congrats?(?:ulations)?|perfect|y(?:ep|up)|yes(?:\s+yes)?|"
    r"filled(?:\s+it(?:\s+out)?)?|done(?:\s+submitted)?|submitted|finalised|finalized|"
    r"好的|收到|明白|了解|嗯+|行|可以|没问题|谢谢|感谢|好勒|搞定|好哒|真棒|恭喜"
    r")[\s!.。！~…🙏👍👏🥳]*$",
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

# Form / checklist completion acknowledgements (allow short trailing thanks).
_FORM_ACK_RE = re.compile(
    r"(?is)^\s*("
    r"(?:i\s+)?(?:just\s+)?(?:filled(?:\s+it(?:\s+out)?)?|submitted|finalised|finalized)"
    r"(?:\s+(?:the\s+)?form)?|"
    r"done(?:\s+submitted)?|form\s+filled|已填|填好了|提交了|交了"
    r")"
    r"(?:[\s,.，。!！~…🙏👍]*"
    r"(?:thanks?(?:\s+you)?|thx|谢谢|感谢)?)?"
    r"[\s,.，。!！~…🙏👍]*$"
)


# Social greetings / post shares — casual emoji reply, not FAQ.
_SOCIAL_GREETING_RE = re.compile(
    r"^\s*("
    r"(?:gm\s*)+|gn|good\s*morning|good\s*evening|good\s*night|"
    r"hello|hiya|hey(?:\s+team)?|hi(?:\s+team)?|howdy(?:\s+bruv)?|"
    r"(?:great|nice|good|pleasure)\s+to\s+meet\s+you(?:\s+all)?|"
    r"pleased\s+to\s+meet\s+you|"
    r"(?:how(?:'\s*)?s?\s+it\s+going|how\s+are\s+you(?:\s+doing)?|"
    r"how\s+you\s+doing|and\s+you)\??|"
    r"很高兴认识你(?:们)?|幸会|久仰|"
    r"早|早上好|晚安|大家好"
    r")[\s!.。！~…❤️☀️🙏👋🔥🚀✨😊?？]*$",
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

# Clear project updates / acknowledgements that may mention Roy or contain
# delivery keywords, but do not ask the bot to do or explain anything.  These
# should be recorded as "no reply needed", not as failed FAQ answers.
_NON_ACTIONABLE_UPDATE_RE = re.compile(
    r"\b("
    r"quick\s+update|status\s+update|just\s+an?\s+update|"
    r"on\s+it|it\s+works(?:\s+now)?|works\s+now|"
    r"we(?:'ve|\s+have)\s+(?:completed|finished|deployed|submitted|updated)|"
    r"(?:is|are|still)\s+in\s+progress|will\s+be\s+ready|"
    r"we\s+will\s+(?:inform|update|announce|engage)|"
    r"we\s+need\s+\d+\s*[-–]\s*\d+\s+days|"
    r"testnet.*(?:done|complete|in\s+doc|ready)|"
    r"for\s+now.*(?:okay|fine|good)|"
    r"thanks?\s+(?:for|roy\b)|thank\s+you\s+for|"
    r"got\s+it|makes\s+sense|sounds\s+good|"
    r"new\s+(?:x|twitter)\s+post|just\s+posted|"
    r"now\s+live(?:\s+on\s+(?:bot\s*)?chain(?:\s+mainnet)?)?|"
    r"(?:is|are)\s+(?:now\s+)?live\s+on\s+(?:bot\s*)?chain(?:\s+mainnet)?|"
    r"officially\s+deployed\s+on\s+(?:bot\s*)?chain"
    r")\b"
    r"|(?:进度|状态)(?:同步|更新)"
    r"|(?:已经|已)(?:完成|部署|提交|更新|解决)"
    r"|(?:正在|仍在)(?:处理|进行|开发|部署)"
    r"|(?:后续|完成后)(?:通知|同步|更新)"
    r"|(?:已上线|正式上线|主网上线)",
    re.IGNORECASE,
)

# A message can omit a question mark and still contain a real request.  Keep
# these in the FAQ/human-decision path even if they also contain update words.
_ACTION_REQUEST_RE = re.compile(
    r"\b("
    r"please\s+(?:check|help|advise|confirm|share|send|provide|review)|"
    r"need\s+(?:your|you\s+to|help|support|from\s+you)|"
    r"could\s+use\s+(?:your\s+)?help|"
    r"the\s+(?:issue|problem)\s+is|"
    r"unable\s+to|cannot\s+|can't\s+|blocked\s+by|"
    r"what\s+we\s+need\s+from\s+you|"
    r"additional\s+(?:help|step|support|information)"
    r")\b"
    r"|(?:请|麻烦)(?:检查|确认|提供|协助|帮忙|回复)"
    r"|(?:需要|希望)(?:你|你们|协助|帮助|支持)"
    r"|(?:问题|异常|错误)(?:是|在于|仍然|还在)",
    re.IGNORECASE,
)

# @username / @channel style tokens (Telegram usernames)
_MENTION_TOKEN_RE = re.compile(r"@[\w\d_]{3,32}", re.IGNORECASE)
# leftover after stripping mentions: whitespace / punctuation only
_TRIVIAL_RE = re.compile(r"^[\s\W_]*$", re.UNICODE)

# XOR into casual-reply RNG so sibling bots never pick the same line
_CASUAL_REPLY_SEED_SALT = 5394265

_SOCIAL_REPLIES_EN = (
    "Hey! 👋",
    "Nice to meet you too 🙌",
    "gm! ☀️",
    "Hi — good to connect",
    "Hey there 👋",
    "Welcome! ✨",
)

_SOCIAL_REPLIES_ZH = (
    "你好 👋",
    "幸会～",
    "早呀 ☀️",
    "嗨嗨",
    "见到你很高兴 ✨",
    "在的 👋",
)

_SHARE_REPLIES_EN = (
    "Nice post 🔥",
    "Love this, thanks for sharing 🙌",
    "Clean update 🚀",
    "Great share — cheers! ✨",
    "Saw the post, solid 🔥",
)

_SHARE_REPLIES_ZH = (
    "好看 🔥",
    "感谢分享 🙌",
    "这条不错 🚀",
    "已阅，赞 ✨",
    "支持一波 🙏",
)

# Short ack replies — casual, never FAQ.
_ACK_REPLIES_EN = (
    "👍",
    "Got it 👍",
    "Cool 🙌",
    "Works for me!",
    "Perfect 👌",
    "Alright!",
    "Noted 👍",
    "👍👍",
)
_ACK_REPLIES_ZH = (
    "👍",
    "好的 👍",
    "收到～",
    "嗯嗯",
    "OK 👌",
    "好嘞",
    "可以可以 🙌",
    "行～",
    "好的好的 🙌",
    "也谢谢耐心～",
)
_CLOSE_ACK_REPLIES_EN = (
    "all good 🙌",
    "appreciate you too 👍",
    "nice — thanks for the patience",
    "perfect, we're good",
)
_CLOSE_ACK_REPLIES_ZH = (
    "好的好的 🙌",
    "也谢谢耐心～",
    "搞定～",
)




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
    without_mentions = _MENTION_TOKEN_RE.sub(" ", stripped)
    without_mentions = re.sub(r"\s+", " ", without_mentions).strip()
    if not without_mentions:
        return False
    if _SOCIAL_GREETING_RE.match(without_mentions):
        return True
    # Short greeting with a name prefix: "Yo Clem gm gm. howdy bruv?"
    if (
        len(without_mentions) <= 90
        and not _ACTION_REQUEST_RE.search(without_mentions)
        and re.search(
            r"(?i)\b((?:gm\s*)+|gn|howdy|good\s*morning|good\s*evening|nice\s+to\s+meet)\b",
            without_mentions,
        )
        and not re.search(
            r"(?i)\b(deploy|mainnet|contract|wallet|audit|grant|sdk|rpc|form|verify|"
            r"what|how|when|where|why|who|which|can|could|would|should)\b",
            without_mentions,
        )
    ):
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
    """Warm greeting or share reply; language follows the message loosely."""
    import random

    cjk = sum(1 for c in (text or "") if "\u4e00" <= c <= "\u9fff")
    if _X_LINK_RE.search(text or ""):
        pool = _SHARE_REPLIES_ZH if cjk >= 2 else _SHARE_REPLIES_EN
    else:
        pool = _SOCIAL_REPLIES_ZH if cjk >= 2 else _SOCIAL_REPLIES_EN
    rng = random.Random((seed or 0) ^ _CASUAL_REPLY_SEED_SALT)
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
    rng = random.Random((seed or 0) ^ _CASUAL_REPLY_SEED_SALT)
    return rng.choice(pool)

def pick_casual_reply(text: str, *, seed: int | None = None) -> str:
    """Social greeting/share → social pool; short ack → ack pool."""
    if is_social_chitchat(text):
        return pick_social_reply(text, seed=seed)
    return pick_ack_reply(text, seed=seed)


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



# Delivery-team alerts: verify asks + mainnet go-live notices.
# Never FAQ / never retrieval — queue human_review + Lark 交付部.
_VERIFY_ASK_RE = re.compile(
    r"(?is)\b("
    r"(?:please|kindly|pls)\s+(?:help\s+(?:me\s+)?(?:to\s+)?)?verify|"
    r"(?:can|could|would)\s+you\s+(?:please\s+|kindly\s+)?"
    r"(?:help\s+(?:me\s+)?(?:to\s+)?)?verify|"
    r"help\s+(?:me\s+)?(?:to\s+)?verify|"
    r"verify\s+(?:the\s+)?(?:mainnet|deployment|deploy(?:ed)?|contract|contracts|"
    r"dapp|front\s*end|frontend|site|website|it|this|here|now|everything)|"
    r"mainnet\s+verif(?:y|ication)|"
    r"verif(?:y|ication)\s+(?:on\s+)?mainnet|"
    r"mainnet\s+verification|"
    r"verify\s+(?:and\s+)?(?:let|check|look)"
    r")\b"
    r"|(?:请|麻烦|帮忙).{0,10}(?:核实|验证|核查)"
    r"|主网.{0,8}(?:核实|验证|核查)|(?:核实|验证|核查).{0,8}主网"
)
_MAINNET_LIVE_RE = re.compile(
    r"(?is)\b("
    r"now\s+live\s+on\s+(?:bot\s*)?chain(?:\s+mainnet)?|"
    r"(?:is|are)\s+(?:now\s+)?live\s+on\s+(?:bot\s*)?chain(?:\s+mainnet)?|"
    r"officially\s+deployed\s+on\s+(?:bot\s*)?chain(?:\s+mainnet)?|"
    r"live\s+on\s+bot\s*chain\s+mainnet|"
    r"deployed\s+on\s+bot\s*chain\s+mainnet"
    r")\b"
    r"|(?:已上线|正式上线|主网上线)"
)
_VERIFY_TECH_EXCLUDE_RE = re.compile(
    r"(?is)\b("
    r"how\s+to\s+verify|programmatically|blockscout|attestation|isBoWallet|"
    r"signature\s+verif|verify\s+that\s+a\s+signature|wallet-specific|"
    r"sdk|oracle|chainlink|grant\s+structure"
    r")\b"
    r"|怎么验证签名|签名验证|预言机"
)
_VERIFY_SELF_RE = re.compile(
    r"(?is)^\s*(?:ok[,.]?\s+|okay[,.]?\s+|sure[,.]?\s+)?"
    r"(?:let\s+me|i(?:\'|\s+a)?ll|i\s+will|i\s+can|we(?:\'|\s+wi)?ll)\s+verify\b"
)
_VERIFY_NEGATE_RE = re.compile(
    r"(?is)\b(?:don\'?t|do\s+not|no\s+need|need\s+not|不必|不需要|不用).{0,24}verif"
)


def delivery_alert_kind(text: str) -> str | None:
    """Return alert kind for Lark/看板, or None if not an alert.

    - ``verify``: ask delivery to verify / mainnet verification status
    - ``mainnet_live``: project announces live on BOT Chain Mainnet
    """
    stripped = (text or "").strip()
    if not stripped:
        return None
    without = _MENTION_TOKEN_RE.sub(" ", stripped)
    without = re.sub(r"\s+", " ", without).strip()
    if not without:
        return None

    # Mainnet go-live announcements (allow longer posts with contract links)
    if len(without) <= 1200 and _MAINNET_LIVE_RE.search(without):
        if not _VERIFY_TECH_EXCLUDE_RE.search(without):
            return "mainnet_live"

    if len(without) > 500:
        return None
    if _VERIFY_TECH_EXCLUDE_RE.search(without):
        return None
    if _VERIFY_SELF_RE.search(without):
        return None
    if _VERIFY_NEGATE_RE.search(without):
        return None
    if _VERIFY_ASK_RE.search(without):
        return "verify"
    # Bare short "verify" / "mainnet verify" after stripping mentions
    if len(without) <= 80 and re.search(
        r"(?is)^(?:hey|hi|hello)?[\s,]*"
        r"(?:mainnet\s+)?verif(?:y|ication)(?:\s+mainnet)?[\s!.。！?？~…🙏👍]*$",
        without,
    ):
        return "verify"
    return None


def is_human_verify_request(text: str) -> bool:
    """True for delivery verify / mainnet-live alerts (no FAQ retrieval)."""
    return delivery_alert_kind(text) is not None


def is_ack_or_chitchat(text: str) -> bool:
    """True for short acknowledgements that must not trigger FAQ."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    without = _MENTION_TOKEN_RE.sub(" ", stripped)
    without = re.sub(r"\s+", " ", without).strip()
    if not without:
        # Bare @mention ping (e.g. @all) is not an acknowledgement.
        return False
    if _ACK_RE.match(without):
        return True
    if len(without) <= 120 and _SOFT_CLOSE_ACK_RE.match(without):
        return True
    if len(without) <= 160 and _FORM_ACK_RE.match(without):
        return True
    # Short social/status check-ins (e.g. "Everything is going great, and you?")
    if (
        len(without) <= 100
        and re.search(
            r"(?i)\b("
            r"going great|hope you (?:slept|are)|how(?:'\s*)?s it going|"
            r"how are you(?: doing)?|how you doing|and you"
            r")\b",
            without,
        )
        and not _ACTION_REQUEST_RE.search(without)
        and not re.search(
            r"(?i)\b(deploy|mainnet|contract|wallet|audit|grant|sdk|rpc)\b",
            without,
        )
    ):
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


def is_non_actionable_update(text: str) -> bool:
    """Return True for clear updates/acknowledgements with no direct ask.

    This intentionally stays conservative. Ambiguous complaints or requests
    continue into RAG/LLM rather than being silently discarded.
    """
    stripped = (text or "").strip()
    if not stripped or looks_like_question(stripped):
        return False
    if _ACTION_REQUEST_RE.search(stripped):
        return False
    without_mentions = _MENTION_TOKEN_RE.sub(" ", stripped)
    without_mentions = re.sub(r"\s+", " ", without_mentions).strip()
    return bool(_NON_ACTIONABLE_UPDATE_RE.search(without_mentions))


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
