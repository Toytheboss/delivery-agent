"""RAG: retrieve knowledge and generate a reply via LLM (optional)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.config_loader import AppConfig
    from bot.knowledge import KnowledgeBase, SearchHit

logger = logging.getLogger(__name__)

NEEDS_HUMAN = "NEEDS_HUMAN"

PROVIDER_DEFAULTS = {
    "deepseek": {
        "env_keys": ("DEEPSEEK_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"),
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "openai": {
        "env_keys": ("OPENAI_API_KEY", "LLM_API_KEY"),
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
}


@dataclass
class ReplyDecision:
    should_reply: bool
    text: str
    reason: str
    best_score: float = 0.0
    language: str = "zh"


@dataclass
class LlmCredentials:
    api_key: str
    base_url: str
    model: str
    provider: str


def _contains_blocked_topic(text: str, blocked: list[str]) -> bool:
    """Return True if a blocked topic appears in the user question.

    English topics use whole-word matching so ``quote`` does not match ``Quoter``.
    CJK topics keep substring matching.
    """
    lowered = text.lower()
    for topic in blocked:
        topic = (topic or "").lower().strip()
        if not topic:
            continue
        if re.search(r"[a-z]", topic):
            if re.search(rf"(?<![a-z0-9_]){re.escape(topic)}(?![a-z0-9_])", lowered):
                return True
        elif topic in lowered:
            return True
    return False


_URL_RE = re.compile(r"https?://[^\s<>\"'）】\]]+|wss://[^\s<>\"'）】\]]+", re.I)
_SOURCE_LINE_RE = re.compile(
    r"(?:【来源】|Source:\s*)(.+)",
    re.I,
)


def _normalize_url(url: str) -> str:
    # Strip common trailing punctuation (incl. CJK) that often follows links in KB text
    return (url or "").strip().rstrip(".,;:)）。、】》\"'")


def _extract_urls(text: str) -> list[str]:
    """Collect http(s)/wss URLs from KB text, preserving order and uniqueness."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in _URL_RE.findall(text or ""):
        url = _normalize_url(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _source_urls_from_chunk(chunk_text: str) -> list[str]:
    """Prefer labeled source/doc links; fall back to any URL in the chunk."""
    preferred: list[str] = []
    seen: set[str] = set()
    for line in (chunk_text or "").splitlines():
        m = _SOURCE_LINE_RE.search(line.strip())
        if not m:
            continue
        for url in _extract_urls(m.group(1)):
            if url not in seen:
                seen.add(url)
                preferred.append(url)
    if preferred:
        return preferred
    return _extract_urls(chunk_text)


def _format_context(hits: list[SearchHit]) -> str:
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        links = _source_urls_from_chunk(hit.chunk.text)
        link_block = ""
        if links:
            link_block = "\nRelated links (include in reply if relevant):\n" + "\n".join(
                links
            )
        parts.append(
            f"[{i}] ({hit.chunk.source}, score={hit.score:.2f})\n"
            f"{hit.chunk.text}{link_block}"
        )
    return "\n\n---\n\n".join(parts)


def _urls_for_reply(hits: list[SearchHit], max_links: int = 3) -> list[str]:
    """Collect reply-worthy URLs: labeled sources first, then other URLs in hits."""
    preferred: list[str] = []
    others: list[str] = []
    seen: set[str] = set()
    for hit in hits[:3]:
        text = hit.chunk.text
        source_urls = set()
        for line in (text or "").splitlines():
            m = _SOURCE_LINE_RE.search(line.strip())
            if not m:
                continue
            for url in _extract_urls(m.group(1)):
                source_urls.add(url)
                if url not in seen:
                    seen.add(url)
                    preferred.append(url)
        for url in _extract_urls(text):
            if url in source_urls or url in seen:
                continue
            seen.add(url)
            others.append(url)
    return (preferred + others)[:max_links]


def _append_missing_links(answer: str, hits: list[SearchHit], max_links: int = 3) -> str:
    """If the reply omitted URLs present in top hits, append a short link block."""
    text = (answer or "").strip()
    if not text or not hits:
        return text
    # Only backfill when the model gave prose with no links at all
    if _extract_urls(text):
        return text

    missing = _urls_for_reply(hits, max_links=max_links)
    if not missing:
        return text
    return text.rstrip() + "\n" + "\n".join(missing)


_RELATED_Q_RE = re.compile(r"【相关问题】\s*(.+)")


def _related_question(chunk_text: str) -> str:
    m = _RELATED_Q_RE.search(chunk_text or "")
    return (m.group(1) if m else chunk_text[:240]).lower()


def _chunk_blob(hit: SearchHit) -> str:
    return (hit.chunk.text or "").lower()


def _asks_wallet_sdk(question: str) -> bool:
    q = (question or "").lower()
    has_sdk_api = "sdk" in q or re.search(r"(?<![a-z])api(?![a-z])", q) is not None
    has_wallet = "wallet" in q or "钱包" in (question or "")
    return bool(has_sdk_api and has_wallet)


def _hit_has_wallet(hit: SearchHit) -> bool:
    blob = _chunk_blob(hit)
    text = hit.chunk.text or ""
    return (
        "bo wallet" in blob
        or "钱包" in text
        or re.search(r"(?<![a-z\-])wallet(?![a-z\-])", blob) is not None
    )


def _hit_has_sdk_api(hit: SearchHit) -> bool:
    blob = _chunk_blob(hit)
    return "sdk" in blob or re.search(r"(?<![a-z])api(?![a-z])", blob) is not None


def _hits_on_topic(question: str, hits: list[SearchHit]) -> list[SearchHit]:
    """Prefer on-topic chunks; do not hard-wipe wallet/SDK hits to empty.

    Previously we required both wallet + sdk/api only in 【相关问题】, which
    dropped all ~0.36 wallet FAQs for「有没有钱包 SDK」even when useful
    context existed in the answer body (or only wallet FAQs were retrieved).
    """
    if not hits or not _asks_wallet_sdk(question):
        return hits

    # Strict: full chunk covers wallet + sdk/api (related Q, keywords, answer)
    strict = [h for h in hits if _hit_has_wallet(h) and _hit_has_sdk_api(h)]
    if strict:
        return strict

    # Soft: keep wallet-topic hits (drop robot-SDK / price-API-only noise).
    # Lets retrieval surface BO Wallet FAQs at ~0.28+; LLM still outputs
    # NEEDS_HUMAN when context cannot answer the SDK question.
    soft: list[SearchHit] = []
    for hit in hits:
        if not _hit_has_wallet(hit):
            continue
        blob = _chunk_blob(hit)
        if "robot connector" in blob or "robot connectors" in blob:
            continue
        soft.append(hit)
    return soft if soft else hits


def _hit_dedupe_key(hit: SearchHit) -> str:
    return f"{hit.chunk.source}\0{hit.chunk.text[:160]}"


def _merge_hits(*groups: list[SearchHit], top_k: int) -> list[SearchHit]:
    """Merge hit lists, keep best score per chunk, return top_k."""
    best: dict[str, SearchHit] = {}
    for group in groups:
        for hit in group:
            key = _hit_dedupe_key(hit)
            prev = best.get(key)
            if prev is None or hit.score > prev.score:
                best[key] = hit
    merged = sorted(best.values(), key=lambda h: h.score, reverse=True)
    return merged[: max(top_k, 0)]


def _rewrite_query_for_search(
    question: str,
    config: "AppConfig",
    creds: LlmCredentials,
) -> str:
    """Rewrite casual Q into short CN+EN search keywords. Fall back to original."""
    q = (question or "").strip()
    if not q:
        return q
    try:
        OpenAI = _get_openai_client_class()
        client = OpenAI(api_key=creds.api_key, base_url=creds.base_url)
        resp = client.chat.completions.create(
            model=creds.model,
            temperature=0.0,
            max_tokens=64,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rewrite the user question into short FAQ search keywords "
                        "for a Delivery Agent knowledge base. Output ONE line only: "
                        "key product terms in Chinese and English "
                        "(mix of the asker's own topic words; never invent a "
                        "product the user did not mention). Keep proper nouns. "
                        "If the input is only an @mention or empty, output exactly: SKIP. "
                        "No sentences, no quotes, no explanation."
                    ),
                },
                {"role": "user", "content": q[:400]},
            ],
        )
        rewritten = (resp.choices[0].message.content or "").strip()
        rewritten = re.sub(r"^[`'\"“”]+|[`'\"“”]+$", "", rewritten)
        rewritten = rewritten.splitlines()[0].strip() if rewritten else ""
        # Reject empty / too long / clearly prose answers / SKIP sentinel
        if not rewritten or len(rewritten) > 160 or rewritten.lower() == q.lower():
            return q
        if rewritten.upper() == "SKIP":
            return q
        if rewritten.startswith("抱歉") or rewritten.startswith("Sorry"):
            return q
        return rewritten
    except Exception as exc:  # noqa: BLE001
        logger.info("Query rewrite failed, using original: %s", exc)
        return q


def _retrieve_hits(
    question: str,
    kb: "KnowledgeBase",
    config: "AppConfig",
    creds: LlmCredentials | None,
) -> list[SearchHit]:
    """Search with rewritten query; if weak, also merge original-query hits."""
    top_k = max(int(config.top_k), 1)
    search_q = question
    if creds is not None:
        search_q = _rewrite_query_for_search(question, config, creds)
        if search_q != question:
            logger.info("Query rewrite: %r → %r", question[:80], search_q[:80])

    primary = _hits_on_topic(question, kb.search(search_q, top_k=top_k))
    best = primary[0].score if primary else 0.0
    weak = (not primary) or (best < config.min_relevance_score)

    if weak and search_q.strip().lower() != (question or "").strip().lower():
        secondary = _hits_on_topic(question, kb.search(question, top_k=top_k))
        return _merge_hits(primary, secondary, top_k=top_k)
    return primary


def detect_reply_language(question: str, config_language: str = "auto") -> str:
    """Return 'en' or 'zh' for reply language based on the user's question."""
    if config_language in ("en", "english"):
        return "en"
    if config_language in ("zh", "cn", "chinese"):
        return "zh"

    text = question or ""
    letters = sum(1 for c in text if c.isascii() and c.isalpha())
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")

    # Any clear Chinese in the question → reply in Chinese
    if cjk >= 1 and cjk >= letters:
        return "zh"
    if cjk >= 2:
        return "zh"
    # Latin-letter questions (including short ones like "RPC?") → English
    if letters >= 2 and letters > cjk:
        return "en"
    # Default: Chinese for ambiguous / emoji-only project-side pings
    return "zh"


def _extract_labeled_answer(chunk_text: str, label: str) -> str:
    match = re.search(
        rf"【{re.escape(label)}】(.+?)(?:\n【(?:参考回答-中文|参考回答-英文|来源)】|\Z)",
        chunk_text,
        re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _clean_fallback_answer(body: str) -> str:
    """Drop internal notes that must never go to users."""
    text = body or ""
    text = re.sub(r"(?m)^【对外口径注意】.*(?:\n|$)", "", text)
    text = re.sub(r"(?m)^\[Do not overpromise\].*(?:\n|$)", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _silent_decision(
    reason: str, best_score: float = 0.0, language: str = "zh"
) -> ReplyDecision:
    """Do not reply when KB/LLM cannot answer (no handoff text)."""
    return ReplyDecision(False, "", reason, best_score, language=language)


def _labeled_answer_from_hits(hits: list[SearchHit], lang: str) -> tuple[str, SearchHit | None]:
    """Prefer a hit that actually contains a labeled answer body."""
    primary = ("参考回答-英文", "参考回答-中文") if lang == "en" else (
        "参考回答-中文",
        "参考回答-英文",
    )
    for hit in hits:
        for label in primary:
            body = _extract_labeled_answer(hit.chunk.text, label)
            if body:
                return body, hit
    return "", hits[0] if hits else None


def _significant_tokens(text: str) -> set[str]:
    """Tokens for a cheap grounding check (EN words + CJK bigrams)."""
    lowered = (text or "").lower()
    words = set(re.findall(r"[a-z0-9]{4,}", lowered))
    cjk = re.findall(r"[\u4e00-\u9fff]+", text or "")
    bigrams: set[str] = set()
    for run in cjk:
        if len(run) == 1:
            bigrams.add(run)
        else:
            bigrams.update(run[i : i + 2] for i in range(len(run) - 1))
    return words | bigrams


def _answer_grounded_in_context(answer: str, context: str, question: str) -> bool:
    """False when the reply barely overlaps question+context (likely off-topic)."""
    ans_tokens = _significant_tokens(answer)
    if len(ans_tokens) < 4:
        # Very short replies (yes/link) — don't over-filter
        return True
    base = _significant_tokens(f"{question}\n{context}")
    if not base:
        return False
    overlap = len(ans_tokens & base)
    ratio = overlap / max(len(ans_tokens), 1)
    return overlap >= 2 and ratio >= 0.18


def _fallback_compose(
    question: str,
    hits: list[SearchHit],
    lang: str,
    *,
    min_score: float = 0.35,
) -> ReplyDecision:
    if not hits:
        return _silent_decision("no relevant knowledge", 0.0)
    best = hits[0]
    if best.score < min_score:
        return _silent_decision("low relevance", best.score)

    body, used = _labeled_answer_from_hits(hits, lang)
    if not body and used is not None:
        body = used.chunk.text.strip()
    body = _clean_fallback_answer(body)
    # Drop absorb markdown chrome if we still fell back to the raw chunk
    if body.startswith("# 学习记录") or body.startswith("<!--"):
        labeled, _ = _labeled_answer_from_hits(hits, lang)
        if labeled:
            body = _clean_fallback_answer(labeled)
    body = _append_missing_links(body, hits)
    # Keep fallback short — no long preamble
    if len(body) > 500:
        body = body[:500].rstrip() + "…"
    return ReplyDecision(True, body, "retrieval fallback", best.score, language=lang)


def split_reply_bubbles(text: str) -> list[str]:
    """Split LLM output into short chat bubbles (separator line: ---)."""
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.split(r"\n\s*---\s*\n", raw)
    bubbles = [p.strip() for p in parts if p.strip()]
    return bubbles or [raw]


# Trailing clarifying asks (e.g. 「需要哪家…？」「要我再发吗」) — drop, don't ping user.
_CLARIFY_ASK_RE = re.compile(
    r"(需要哪家|要哪家|哪一家|哪家的|需要我再|要我再发|要不要我|"
    r"还需要什么|还要什么|告诉我(一下)?哪|"
    r"which (one|project|company|chain)|want me to (send|share)|"
    r"shall I|should I (send|share)|do you (want|need)|"
    r"need (me to|more detail)|let me know which)",
    re.I,
)


def _is_clarifying_question_bubble(text: str) -> bool:
    """True if bubble is mainly asking the user to clarify (not mid-FAQ content)."""
    t = (text or "").strip()
    if not t or len(t) > 160:
        return False
    ends_q = t.endswith("?") or t.endswith("？")
    if ends_q and _CLARIFY_ASK_RE.search(t):
        return True
    if ends_q and re.search(r"(哪家|哪个|哪一|吗|么|what|which|want me)", t, re.I):
        return True
    # Same ask without 「？」 (common in CN chat): 「需要哪家的…我再单独发你」
    if _CLARIFY_ASK_RE.search(t) and re.search(
        r"(再(单独)?发|再发你|告诉我|发你|吗$|哪)", t
    ):
        return True
    return False


def _strip_clarifying_tail(answer: str) -> str:
    """Drop trailing clarifying-question bubbles; keep substance + links."""
    bubbles = split_reply_bubbles(answer)
    if not bubbles:
        return (answer or "").strip()
    while bubbles and _is_clarifying_question_bubble(bubbles[-1]):
        bubbles.pop()
    if not bubbles:
        return ""
    return "\n---\n".join(bubbles)


def resolve_llm_credentials(config: AppConfig) -> LlmCredentials | None:
    provider = config.llm_provider
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["deepseek"])

    api_key = ""
    for key_name in defaults["env_keys"]:
        api_key = os.getenv(key_name, "").strip()
        if api_key:
            break

    if not api_key:
        return None

    base_url = config.llm_base_url or defaults["base_url"]
    model = config.llm_model or defaults["model"]
    return LlmCredentials(
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider=provider,
    )


_OpenAIClient = None


def _get_openai_client_class():
    """Import openai once (avoids reloading native pydantic_core on every reply)."""
    global _OpenAIClient
    if _OpenAIClient is None:
        try:
            from openai import OpenAI as _OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package not installed") from exc
        _OpenAIClient = _OpenAI
    return _OpenAIClient


def _call_llm(
    question: str,
    context: str,
    config: AppConfig,
    creds: LlmCredentials,
    lang: str,
) -> str:
    OpenAI = _get_openai_client_class()
    client = OpenAI(api_key=creds.api_key, base_url=creds.base_url)

    if lang == "en":
        language_rule = (
            "CRITICAL LANGUAGE LOCK: Partner asked in English → reply entirely in English. "
            "If context is Chinese, translate the needed facts. No Chinese sentences "
            "(proper nouns / tickers / URLs ok)."
        )
        system = (
            "You're Roy (Delivery Agent delivery PM) typing in a Telegram project group — "
            "not a helpdesk bot, not corporate support.\n"
            "Answer ONLY this question, ONLY from the context below.\n"
            "If you are not confident the context directly answers it, stay silent.\n"
            "Grounding:\n"
            "- Context must match the same topic (Wallet SDK ≠ chain RPC; "
            "ecosystem grants ≠ internal delivery SOP).\n"
            "- Off-topic, thin, missing, or only loosely related → output exactly "
            "NEEDS_HUMAN (nothing else; the app will stay silent).\n"
            "- Prefer silence over a plausible-but-wrong reply. "
            "Don't pivot just because keywords overlap. Don't invent chain facts.\n"
            "Links / sources:\n"
            "- When context has relevant docs, help-center, GitHub, form, RPC, "
            "explorer, or other URLs — include them in the reply (don't answer "
            "with prose only).\n"
            "- Prefer putting links on their own line, or clearly after the short "
            "answer. Copy URLs exactly; never invent links not in context.\n"
            "Style / rules:\n"
            "- NEVER ask clarifying questions. Never say 'which one?', "
            "'which project/company?', 'want me to send more?', "
            "'need the detailed list for which?' — just send the answer.\n"
            "- If several options fit, list them all (or the most relevant) "
            "with links in one go; don't ask the user to pick first.\n"
            "- Truly don't know / context insufficient → NEEDS_HUMAN only "
            "(silent). Don't ask the user to clarify. Don't ping colleagues.\n"
            "Tone:\n"
            "1. Casual chat: short, natural, like a colleague — not an essay\n"
            "2. Lead with the answer / next step; skip greetings, empathy fluff, recap\n"
            "3. Prefer 1–3 bubbles, separated by a line with only ---\n"
            "4. ~1–2 sentences per bubble (or a tiny checklist); under ~120 words total\n"
            "5. No markdown headings; no 'Based on the docs', 'Hope this helps', "
            "'As an AI', 'I'd be happy to'\n"
            "6. Never invent pricing, contracts, timelines, listing guarantees, "
            "or SDK/API details not in context\n"
            "7. English question → English only\n"
            "8. Never say 'at crawl time', 'as scraped', 'page overview (crawl)', "
            "or other archive/meta phrasing — just state the numbers like a person\n"
            "9. When giving contract addresses / RPC / links: paste the official "
            "values and doc URL only. Do NOT add scolding asides like "
            "'only use official, don't use DM links' or 'don't copy from chat'"
        )
        user = (
            "Reply language: English ONLY\n\n"
            f"Question:\n{question}\n\n"
            f"Context (may be Chinese — answer in English; "
            f"if it doesn't answer THIS question, output only NEEDS_HUMAN):\n{context}"
        )
    else:
        language_rule = (
            "关键语言锁定：项目方用中文问 → 你全程中文回。"
            "资料里有英文也用中文转述，不要整段英文答。"
        )
        system = (
            "你是 Delivery Agent PM Roy，在 Telegram 项目群里跟项目方聊天——"
            "像同事打字，不像客服机器人，也不要公文腔。\n"
            "只答当前问题，且只能依据下面资料。\n"
            "没把握对上题意时保持沉默，不要硬答。\n"
            "依据：\n"
            "- 资料要对上同一主题（钱包 SDK ≠ 链 RPC；生态支持 ≠ 内部交付 SOP）\n"
            "- 跑题、太薄、答不上、或只是擦边相关 → 只输出 NEEDS_HUMAN"
            "（别多写；系统会保持沉默不回复）\n"
            "- 宁可沉默，也不要用擦边资料凑一篇看似相关的回复；"
            "别因为关键词碰巧重合就换题答；链上事实别编\n"
            "链接/来源：\n"
            "- 资料里若有相关文档、帮助中心、GitHub、表单、RPC、浏览器等链接，"
            "回复里必须带上（不要只写文字不给链接）\n"
            "- 链接优先单独一行，或紧接在短结论后面；原样复制，禁止编造资料没有的链接\n"
            "风格/规则：\n"
            "- 禁止反问澄清。不要说「要哪家」「需要哪家的详细报道」"
            "「需要我再发吗」「要我单独发你吗」——直接把内容发出去。\n"
            "- 若有多个选项/多家资料，一次列全（或列最相关几条并带链接），"
            "不要先问对方要哪家。\n"
            "- 真不知道 / 资料不够 → 只输出 NEEDS_HUMAN（沉默）。"
            "不要让用户补充信息，不要拉同事。\n"
            "口吻：\n"
            "1. 口语、短、自然；别长篇，别端着\n"
            "2. 先给结论/下一步；少寒暄、少铺垫、少复述问题\n"
            "3. 优先 1–3 条短气泡，用单独一行 --- 分隔\n"
            "4. 每条大概 1–2 句（或很短清单）；全文尽量 ≤150 字\n"
            "5. 不要标题；不要「根据资料」「希望有帮助」「作为 AI」"
            "「很高兴为您服务」这类套话\n"
            "6. 不编造价格、合同、排期、上币承诺，以及资料里没有的 SDK/API 细节\n"
            "7. 中文问题必须中文答\n"
            "8. 禁止「抓取时」「页面公开概览（抓取时）」「crawl-time」等档案腔——"
            "有数字就直接说，像同事随口报\n"
            "9. 给合约地址 / RPC / 链接时：直接贴官方地址和文档链接即可。"
            "不要加训诫式附言，例如「以官方为准，别用私聊发的」"
            "「不要用私聊节点」「别抄错」这类；需要出处就静静附上官方链接"
        )
        user = (
            "回复语言：仅中文\n\n"
            f"问题：\n{question}\n\n"
            f"资料上下文（若含英文，用中文转述要点；"
            f"若不能直接回答这个问题，只输出 NEEDS_HUMAN）：\n{context}"
        )

    system = f"{language_rule}\n\n{system}"

    if config.reply_rules:
        rules_block = "\n".join(f"- {rule}" for rule in config.reply_rules)
        system = f"{system}\n\nAdditional rules from config:\n{rules_block}"

    response = client.chat.completions.create(
        model=creds.model,
        temperature=config.llm_temperature,
        max_tokens=config.llm_max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()


async def generate_reply(
    question: str,
    kb: KnowledgeBase,
    config: AppConfig,
) -> ReplyDecision:
    lang = detect_reply_language(question, config.reply_language)

    # Sensitive commercial topics: stay silent.
    if _contains_blocked_topic(question, config.blocked_topics):
        return ReplyDecision(
            False, "", "blocked topic in question", 0.0, language=lang
        )

    creds = resolve_llm_credentials(config)
    hits = _retrieve_hits(question, kb, config, creds)
    best_score = hits[0].score if hits else 0.0

    if not hits:
        return _silent_decision("no on-topic knowledge", best_score, language=lang)
    if best_score < config.min_relevance_score:
        return _silent_decision("below min relevance", best_score, language=lang)

    # 仅检查用户问题是否属于敏感询价/承诺；资料上下文常含「不对价格承诺」等说明，不应拦截
    context = _format_context(hits)
    logger.info("Reply language=%s for question=%r", lang, question[:80])

    if creds is None:
        logger.info("No LLM API key set; using retrieval fallback")
        return _fallback_compose(
            question, hits, lang, min_score=config.min_relevance_score
        )

    try:
        answer = _call_llm(question, context, config, creds, lang)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM call failed (%s): %s", creds.provider, exc)
        return _fallback_compose(
            question, hits, lang, min_score=config.min_relevance_score
        )

    if NEEDS_HUMAN in answer or not answer.strip():
        return _silent_decision("llm needs human", best_score, language=lang)

    answer = re.sub(r"\s*NEEDS_HUMAN\s*", "", answer).strip()
    if not answer:
        return _silent_decision("empty llm answer", best_score, language=lang)

    stripped = _strip_clarifying_tail(answer)
    if stripped != answer:
        logger.info("Stripped clarifying-question tail from LLM reply")
        answer = stripped
    if not answer:
        return _silent_decision(
            "clarifying-only reply stripped", best_score, language=lang
        )

    if not _answer_grounded_in_context(answer, context, question):
        logger.info(
            "Silencing poorly grounded reply (score=%.3f, q=%r)",
            best_score,
            question[:80],
        )
        return _silent_decision("answer not grounded", best_score, language=lang)

    answer = _append_missing_links(answer, hits)
    return ReplyDecision(
        True, answer, f"llm:{creds.provider}:{lang}", best_score, language=lang
    )
