"""Short social replies: fixed lexicon, per-chat memory, one bot at a time.

Praise, thanks, and plain acks become a 👍 or 🔥 reaction. Greetings, link
shares, and sign-offs still send a short line from the matching list.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon.tl.custom.message import Message

logger = logging.getLogger(__name__)

_CASUAL_REPLY_SEED_SALT = 5394265
_PEER_WINDOW_SECONDS = 120
_RECENT_LIMIT = 15
_CLAIM_TTL_SECONDS = 6 * 3600
_REACT_EMOJIS = ("👍", "🔥")

_MENTION_TOKEN_RE = re.compile(r"@[\w\d_]{3,32}", re.IGNORECASE)
_X_LINK_RE = re.compile(
    r"https?://(?:(?:www|mobile)\.)?(?:x\.com|twitter\.com|t\.co)/\S+",
    re.IGNORECASE,
)

_THANKS_RE = re.compile(
    r"(?is)^\s*(?:"
    r"thanks?(?:\s+you)?(?:\s+for\s+[a-z0-9']+(?:\s+[a-z0-9']+){0,5})?|"
    r"thx|ty|appreciate(?:\s+(?:it|you|this|that))?|"
    r"谢谢(?:你|您)?(?:啊|呀|啦)?(?:分享|支持|耐心)?|"
    r"感谢(?:你|您|分享|支持|耐心)?|辛苦了?"
    r")[\s!.。！~…🙏👍]*$"
)
_PRAISE_RE = re.compile(
    r"(?is)^\s*(?:"
    r"awesome|nice(?:\s+one)?|great|love\s+(?:it|this|that)|solid|"
    r"perfect|congrats?(?:ulations)?|cool|so\s+good|looks\s+good|"
    r"不错|厉害|太好了|真棒|恭喜|漂亮|稳了"
    r")[\s!.。！~…🙏👍🔥]*$"
)
_ACK_LINE_RE = re.compile(
    r"(?is)^\s*(?:"
    r"will do|got it|sounds good|makes sense|noted|lgtm|sure+|ok(?:ay|ey)?|"
    r"np|no problem|roger|alright|y(?:ep|up)|yes|"
    r"好的|收到|明白|了解|嗯+|行|可以|没问题|好勒|搞定|好哒"
    r")[\s!.。！~…🙏👍]*$"
)
_GREETING_RE = re.compile(
    r"(?is)^\s*(?:"
    r"(?:gm\s*)+|gn|good\s*morning|good\s*evening|good\s*night|"
    r"hello|hiya|hey(?:\s+team)?|hi(?:\s+team)?|howdy|"
    r"how(?:'s|\s+is)\s+it\s+going|how\s+are\s+you(?:\s+doing)?|"
    r"how\s+you\s+doing|"
    r"早+|早上好|晚安|大家好|你好|晚上好|嗨+"
    r")[\s!.。！~…❤️☀️🙏👋]*$"
)
_CLOSE_RE = re.compile(
    r"(?is)^\s*(?:"
    r"(?:all\s+)?done(?:\s+here)?|we(?:'re|\s+are)\s+good|all\s+good|"
    r"appreciate(?:\s+the)?\s+patience|thanks?\s+for\s+(?:the\s+)?patience|"
    r"感谢耐心|搞定了|弄好了|处理好了"
    r")[\s!.。！~…👍🙏]*$"
)
_MORNING_TEXT_RE = re.compile(
    r"(?i)\b(?:gm|morning)\b|早"
)
_NIGHT_TEXT_RE = re.compile(
    r"(?i)\b(?:gn|night|evening)\b|晚安|晚上"
)
_MORNING_LINE_RE = re.compile(r"(?i)\bgm\b|morning|早")
_NIGHT_LINE_RE = re.compile(r"(?i)\b(?:night|evening)\b|晚安|晚上")

_REACT_KINDS = frozenset({"praise", "thanks", "ack"})

_PRAISE_EN = (
    "sounds good", "glad it works", "nice one", "that's great", "love that",
    "solid", "looking good", "nice work", "this is great", "glad to see it",
    "yeah this works", "sweet", "that's the one", "clean", "good stuff",
    "this looks right", "oh nice", "yep, this is good", "that's clean",
    "good to see", "this one's good", "sharp", "that's better", "yeah nice",
    "ok I like this", "this lands", "good good", "that's solid", "I like it",
    "nice nice", "there we go", "👍", "🔥", "nice 🔥", "glad it works 👍",
    "looking sharp",
)
_PRAISE_ZH = (
    "可以", "不错", "挺好", "看着行", "这个好", "好看", "这个对", "成了",
    "挺顺", "喜欢这个", "这个像样", "有了", "对味", "挺干净", "这个稳",
    "看着舒服", "可以可以", "不错不错", "这个我喜欢", "挺到位", "好看多了",
    "这个行", "嗯这个好", "有感觉", "这个顺", "看着对", "挺利落", "这个可以",
    "不错啊", "挺漂亮", "有点东西", "👍", "🔥", "不错 🔥", "这个好 👍", "看着挺稳",
)
_THANKS_EN = (
    "you too", "anytime", "glad to", "appreciate it", "thanks, you too",
    "of course", "no worries", "happy to", "same to you", "cheers", "you bet",
    "likewise", "sure thing", "glad it helped", "anytime, really", "np",
    "right back at you", "appreciate you", "same here", "yeah you too",
    "no problem", "happy to do it", "all good", "got you", "thank you too",
    "course", "yeah anytime", "same", "you too, really", "glad you said",
    "all good here", "👍", "you too 👍", "anytime 👍", "likewise 🔥", "cheers 👍",
)
_THANKS_ZH = (
    "也谢你", "客气", "应该的", "彼此彼此", "也谢谢", "没事", "谢啥", "你也是",
    "同谢", "好说", "客气了", "也谢", "没问题", "应该的呀", "彼此", "你太客气",
    "好说好说", "也谢谢你", "小事", "嗯也谢", "不必谢", "互相的", "你也辛苦",
    "谢你", "客气客气", "也谢谢耐心", "没事没事", "你客气了", "互谢",
    "好说，也谢你", "应该的，你也是", "👍", "也谢你 👍", "客气 🔥", "应该的 👍",
    "彼此 👍",
)
_ACK_EN = (
    "got it", "ok", "noted", "sure", "alright", "yep", "cool", "on it",
    "will do", "heard", "ok ok", "yeah", "copy", "fine", "all good",
    "sure thing", "got that", "ok then", "yep yep", "right", "understood",
    "ok cool", "yeah ok", "noted that", "sounds right", "ok with me", "fair",
    "done", "I'm with you", "ok, heard", "yeah got it", "👍", "🔥", "got it 👍",
    "ok 👍", "yep 🔥",
)
_ACK_ZH = (
    "收到", "好的", "嗯", "行", "好", "嗯嗯", "好嘞", "可以", "行的", "知道了",
    "好的好的", "嗯好", "OK", "明白", "行行", "收到了", "好，知道", "嗯行",
    "可以的", "好啊", "中", "妥", "成", "好，记下了", "嗯，收到", "行，知道了",
    "好的呢", "嗯好的", "收到收到", "好，就这样", "行啊", "👍", "🔥", "收到 👍",
    "好的 👍", "行 🔥",
)
_GREETING_EN = (
    "hey", "hi", "gm", "hello", "hey hey", "yo", "hi there", "morning",
    "gm gm", "hey, you", "hi hi", "hello there", "hey team", "gm, all",
    "hi all", "evening", "night", "hey, morning", "hi, gm", "yo yo",
    "hey hey hey", "good morning", "good to see you", "hi, welcome",
    "hey, welcome in", "gm folks", "hi folks", "hey, how's it going",
    "hi, you around", "morning all", "hey there", "👋", "gm ☀️", "hey 👋",
    "hi 👋", "morning ☀️",
)
_GREETING_ZH = (
    "嗨", "你好", "早", "早上好", "嗨嗨", "在", "早啊", "你好呀", "早早",
    "嗨，在的", "大家好", "早，各位", "晚安", "晚上好", "嗨，来了", "你好，在",
    "早呀", "嗨呀", "在的", "来了", "早，在", "你好你好", "嗨，各位",
    "早，群里好", "嗯嗨", "你好，刚看到", "早，起来了", "嗨，你在", "晚上好呀",
    "晚安啦", "在呢", "👋", "早 ☀️", "嗨 👋", "你好 👋", "早上好 ☀️",
)
_SHARE_EN = (
    "nice post", "saw it", "good one", "clean post", "like this", "solid post",
    "oh this is good", "yeah I saw", "nice, posted", "good share",
    "this one's nice", "read it", "sharp post", "like the post", "good update",
    "saw the post", "nice update", "this reads well", "good post",
    "yeah nice one", "caught it", "post looks good", "I like the post",
    "clean one", "nice, this", "good, saw it", "update looks good",
    "yeah this post", "short and good", "post is clean", "glad you posted",
    "🔥", "👍", "nice post 🔥", "saw it 👍", "good one 🔥",
)
_SHARE_ZH = (
    "这条好", "看到了", "不错这条", "写得干净", "喜欢这条", "这条稳",
    "哦这条可以", "嗯看到了", "发得好", "这条顺", "看了", "这条到位",
    "更新得清楚", "这条我喜欢", "短，好", "发得挺好", "这条清楚", "看着顺",
    "这条行", "嗯，这条不错", "刷到了", "写得挺好", "这条利落", "更新看到了",
    "这条对", "好看这条", "发得干净", "这条有了", "看完了，好", "这条挺稳",
    "这条可以发", "🔥", "👍", "这条好 🔥", "看到了 👍", "不错 🔥",
)
_CLOSE_EN = (
    "all good", "we're good", "appreciate you too", "same here",
    "good, we're set", "yeah all good", "thanks for hanging in", "we're fine",
    "all set", "good from here", "yeah we're good", "appreciate the patience",
    "same, all good", "we're done here", "good, thanks too", "ok we're good",
    "fine on my side", "all clear", "yeah, set", "good good, we're fine",
    "patience appreciated", "we're ok", "all good on this", "yeah, clear",
    "set then", "good, that's it", "fine here", "we're squared",
    "ok, all clear", "good, nothing else", "yeah that's it", "👍",
    "all good 👍", "we're good 👍", "appreciate you too 🔥", "all set 👍",
)
_CLOSE_ZH = (
    "都好", "齐了", "也谢你耐心", "这边好了", "妥了", "好，到这", "没什么了",
    "这边清楚", "好了好了", "齐活", "也辛苦你", "这边 OK", "好，收了",
    "没别的了", "嗯，齐了", "这边搞定", "好，就这些", "清楚了", "行，到这",
    "也谢谢耐心", "这边没事了", "好，结束", "嗯，好了", "都齐", "这边可以了",
    "好，没了", "辛苦，也谢", "行，齐了", "到这儿", "好，清楚", "嗯到这",
    "👍", "都好 👍", "齐了 👍", "也谢你 🔥", "妥了 👍",
)

_POOLS = {
    ("praise", "en"): _PRAISE_EN,
    ("praise", "zh"): _PRAISE_ZH,
    ("thanks", "en"): _THANKS_EN,
    ("thanks", "zh"): _THANKS_ZH,
    ("ack", "en"): _ACK_EN,
    ("ack", "zh"): _ACK_ZH,
    ("greeting", "en"): _GREETING_EN,
    ("greeting", "zh"): _GREETING_ZH,
    ("share", "en"): _SHARE_EN,
    ("share", "zh"): _SHARE_ZH,
    ("close", "en"): _CLOSE_EN,
    ("close", "zh"): _CLOSE_ZH,
}


@dataclass
class CasualDelivery:
    action: str
    body: str = ""
    kind: str = ""
    reason: str = ""


def _strip_mentions(text: str) -> str:
    without = _MENTION_TOKEN_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", without).strip()


def _lang(text: str) -> str:
    cjk = sum(1 for char in text or "" if "\u4e00" <= char <= "\u9fff")
    return "zh" if cjk >= 1 else "en"


def casual_reply_kind(text: str) -> str | None:
    """Classify a short social line. None means leave it to FAQ."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > 180:
        return None
    without = _strip_mentions(stripped)
    if not without:
        return None
    if _X_LINK_RE.search(stripped) and len(without) <= 140:
        if "?" in without or "？" in without:
            return None
        return "share"
    if _GREETING_RE.match(without):
        return "greeting"
    if _CLOSE_RE.match(without):
        return "close"
    if _THANKS_RE.match(without):
        return "thanks"
    if _PRAISE_RE.match(without):
        return "praise"
    if _ACK_LINE_RE.match(without):
        return "ack"
    return None


def _pool_for(kind: str, text: str) -> tuple[str, ...]:
    lang = _lang(text)
    pool = _POOLS[(kind, lang)]
    if kind != "greeting":
        return pool
    if _MORNING_TEXT_RE.search(text):
        narrowed = tuple(line for line in pool if not _NIGHT_LINE_RE.search(line))
    elif _NIGHT_TEXT_RE.search(text):
        narrowed = tuple(line for line in pool if not _MORNING_LINE_RE.search(line))
    else:
        narrowed = tuple(
            line
            for line in pool
            if not _MORNING_LINE_RE.search(line) and not _NIGHT_LINE_RE.search(line)
        )
    return narrowed or pool


def _choose(options: tuple[str, ...] | list[str], recent: list[str], seed: int) -> str:
    fresh = [item for item in options if item not in set(recent[-_RECENT_LIMIT:])]
    choices = fresh or list(options)
    rng = random.Random((seed or 0) ^ _CASUAL_REPLY_SEED_SALT)
    return rng.choice(choices)


def resolve_casual_kind(text: str) -> str | None:
    """Kind for the casual path, including older greeting/ack detectors."""
    kind = casual_reply_kind(text)
    if kind:
        return kind
    from bot.triggers import is_ack_or_chitchat, is_contextless_confirm, is_social_chitchat

    if is_contextless_confirm(text):
        return None
    if is_social_chitchat(text):
        return "share" if _X_LINK_RE.search(text or "") else "greeting"
    if is_ack_or_chitchat(text):
        return "ack"
    return None


def pick_casual_text(text: str, *, seed: int | None = None, recent: list[str] | None = None) -> str:
    kind = resolve_casual_kind(text) or "ack"
    pool = _pool_for(kind, text)
    return _choose(pool, recent or [], seed or 0)


def state_path() -> Path:
    override = os.getenv("CASUAL_REPLY_STATE", "").strip()
    if override:
        return Path(override)
    shared = Path("/opt/botchain-shared/casual_reply_state.json")
    if shared.parent.is_dir():
        return shared
    return Path("data/casual_reply_state.json")


def _blank_state() -> dict:
    return {"claims": {}, "chats": {}, "recent": {}}


def _load_state(raw: str) -> dict:
    if not raw.strip():
        return _blank_state()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _blank_state()
    if not isinstance(data, dict):
        return _blank_state()
    data.setdefault("claims", {})
    data.setdefault("chats", {})
    data.setdefault("recent", {})
    return data


def _prune(state: dict, now: float) -> None:
    claims = state.get("claims") or {}
    stale = [
        key
        for key, row in claims.items()
        if now - float((row or {}).get("ts") or 0) > _CLAIM_TTL_SECONDS
    ]
    for key in stale:
        claims.pop(key, None)
    state["claims"] = claims


def _with_state(mutator):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            state = _load_state(handle.read())
            _prune(state, time.time())
            result = mutator(state)
            handle.seek(0)
            handle.truncate()
            json.dump(state, handle, ensure_ascii=False)
            handle.flush()
            return result
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def begin_casual(chat_id: int, message_id: int, bot_id: str) -> tuple[bool, list[str]]:
    """Claim this message. The other bot stays quiet for two minutes."""
    key = f"{chat_id}:{message_id}"
    chat_key = str(chat_id)

    def mutate(state: dict) -> tuple[bool, list[str]]:
        now = time.time()
        claims = state["claims"]
        chats = state["chats"]
        recent = list((state["recent"].get(chat_key) or [])[-_RECENT_LIMIT:])
        if key in claims:
            return False, recent
        last = chats.get(chat_key) or {}
        last_bot = str(last.get("bot") or "")
        last_ts = float(last.get("ts") or 0)
        if last_bot and last_bot != bot_id and now - last_ts < _PEER_WINDOW_SECONDS:
            return False, recent
        claims[key] = {"bot": bot_id, "ts": now, "prev": last or None}
        chats[chat_key] = {"bot": bot_id, "ts": now}
        return True, recent

    try:
        return _with_state(mutate)
    except OSError:
        logger.exception("casual claim failed; answering anyway")
        return True, []


def finish_casual(chat_id: int, phrase: str) -> None:
    chat_key = str(chat_id)

    def mutate(state: dict) -> None:
        recent = list(state["recent"].get(chat_key) or [])
        recent.append(phrase)
        state["recent"][chat_key] = recent[-_RECENT_LIMIT:]

    try:
        _with_state(mutate)
    except OSError:
        logger.exception("casual memory write failed")


def abort_casual(chat_id: int, message_id: int, bot_id: str) -> None:
    key = f"{chat_id}:{message_id}"
    chat_key = str(chat_id)

    def mutate(state: dict) -> None:
        claim = (state["claims"] or {}).pop(key, None)
        if not claim or claim.get("bot") != bot_id:
            return
        current = (state["chats"] or {}).get(chat_key) or {}
        if current.get("bot") == bot_id and float(current.get("ts") or 0) == float(claim.get("ts") or 0):
            prev = claim.get("prev") or None
            if prev:
                state["chats"][chat_key] = prev
            else:
                state["chats"].pop(chat_key, None)

    try:
        _with_state(mutate)
    except OSError:
        logger.exception("casual claim abort failed")


async def _react(client, message: Message, emoji: str) -> bool:
    from telethon.tl.functions.messages import SendReactionRequest
    from telethon.tl.types import ReactionEmoji

    try:
        peer = await message.get_input_chat()
        await client(
            SendReactionRequest(
                peer=peer,
                msg_id=message.id,
                reaction=[ReactionEmoji(emoticon=emoji)],
            )
        )
        return True
    except Exception:
        logger.warning("Reaction %s failed in chat %s", emoji, message.chat_id, exc_info=True)
        return False


async def deliver_casual(
    client,
    message: Message,
    *,
    chat_id: int,
    text: str,
    bot_id: str,
    seed: int,
    delay: float = 0,
) -> CasualDelivery:
    kind = resolve_casual_kind(text)
    if kind is None:
        return CasualDelivery(action="skip", reason="not_casual")
    allowed, recent = begin_casual(chat_id, message.id, bot_id)
    if not allowed:
        return CasualDelivery(action="skip", kind=kind, reason="peer_already_replied")
    if delay > 0:
        await asyncio.sleep(delay)
    try:
        if kind in _REACT_KINDS:
            emoji = _choose(_REACT_EMOJIS, [item.removeprefix("react:") for item in recent if item.startswith("react:")], seed)
            if await _react(client, message, emoji):
                finish_casual(chat_id, f"react:{emoji}")
                return CasualDelivery(action="reaction", body=emoji, kind=kind, reason="reaction")
        line = _choose(_pool_for(kind, text), recent, seed)
        await message.reply(line)
        finish_casual(chat_id, line)
        return CasualDelivery(action="text", body=line, kind=kind, reason=kind)
    except Exception:
        abort_casual(chat_id, message.id, bot_id)
        raise
