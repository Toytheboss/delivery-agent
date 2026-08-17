"""Knowledge base loading and lightweight retrieval."""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[a-zA-Z0-9_\u4e00-\u9fff]+")
RELATED_RE = re.compile(r"【相关问题】\s*(.+)")
KEYWORDS_RE = re.compile(r"【关键词】\s*(.+)")

# Internal process docs — not for answering project-partner questions
EXCLUDE_SOURCE_PREFIXES = ("lark_",)

# Expand query tokens so 支持≈扶持, 方案≈计划, etc.
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"支持", "扶持", "support", "grant"}),
    frozenset({"方案", "计划", "program", "overview"}),
    frozenset({"地址", "url", "endpoint", "rpc"}),
    frozenset({"钱包", "wallet"}),
    frozenset({"生态", "ecosystem"}),
)


def _expand_synonyms(tokens: set[str]) -> set[str]:
    out = set(tokens)
    for group in _SYNONYM_GROUPS:
        if tokens & group:
            out |= set(group)
    return out


# High-frequency English tokens that must not inflate ASCII keyword bonuses.
_ASCII_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "these",
        "those",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "how",
        "can",
        "does",
        "did",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "you",
        "your",
        "our",
        "any",
        "all",
        "not",
        "but",
        "or",
        "into",
        "about",
        "could",
        "would",
        "should",
        "need",
        "needs",
        "share",
        "latest",
        "official",
        "other",
        "than",
        "then",
        "also",
        "just",
        "only",
        "more",
        "some",
        "such",
        "please",
        "thanks",
    }
)


def _required_topic_terms(query: str) -> list[str]:
    """Product/topic anchors that retrieved chunks should mention.

    For wallet + SDK/API questions, require *wallet* only — never sdk/api as
    must-terms. Many BO Wallet FAQs cover integration without the literal
    "SDK" token; requiring both would wipe hits for「有没有钱包 SDK」.
    """
    q = (query or "").lower()
    must: list[str] = []
    asks_wallet = (
        "bo wallet" in q
        or "钱包" in (query or "")
        or re.search(r"(?<![a-z\-])wallet(?![a-z\-])", q) is not None
    )
    asks_sdk_api = "sdk" in q or re.search(r"(?<![a-z])api(?![a-z])", q) is not None
    if "bo wallet" in q or (asks_wallet and asks_sdk_api):
        must.append("wallet")
    if re.search(r"(?<![a-z])rpc(?![a-z])", q):
        must.append("rpc")
    if re.search(r"(?<![a-z])grant(?![a-z])", q):
        must.append("grant")
    if "生态" in (query or "") or "ecosystem" in q:
        must.append("生态")
    if re.search(r"(?<![a-z])bdex(?![a-z])", q) or "bot dex" in q:
        must.append("bdex")
    return must


def _chunk_mentions(chunk: Chunk, term: str) -> bool:
    blob = chunk.text.lower()
    if term == "生态":
        return (
            "生态" in chunk.text
            or "ecosystem" in blob
            or re.search(r"(?<![a-z])grant(?![a-z])", blob) is not None
        )
    if term == "wallet":
        # Avoid false positives like dex-wallet.botchain.ai
        return (
            "bo wallet" in blob
            or "钱包" in chunk.text
            or re.search(r"(?<![a-z\-])wallet(?![a-z\-])", blob) is not None
        )
    if term == "rpc":
        return re.search(r"(?<![a-z])rpc(?![a-z])", blob) is not None
    if term == "grant":
        return re.search(r"(?<![a-z])grant(?![a-z])", blob) is not None
    if term == "bdex":
        return (
            re.search(r"(?<![a-z])bdex(?![a-z])", blob) is not None
            or "bot dex" in blob
            or "botdex" in blob
        )
    return term in blob


@dataclass
class Chunk:
    source: str
    text: str
    tokens: set[str]
    category: str = ""
    question_tokens: set[str] = field(default_factory=set)
    keyword_tokens: set[str] = field(default_factory=set)


@dataclass
class SearchHit:
    chunk: Chunk
    score: float


def _tokenize(text: str) -> set[str]:
    """Legacy tokenizer kept for compatibility."""
    tokens: set[str] = set()
    for t in TOKEN_RE.findall(text):
        lower = t.lower()
        if len(lower) > 1 or ("\u4e00" <= lower <= "\u9fff"):
            tokens.add(lower)
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            tokens.add(ch)
    return tokens


def _search_tokens(text: str) -> set[str]:
    """Search tokens: English words + Chinese bigrams (skip noisy unigrams)."""
    tokens: set[str] = set()
    for raw in TOKEN_RE.findall(text or ""):
        t = raw.lower()
        if re.fullmatch(r"[a-z0-9_]+", t):
            if len(t) >= 2:
                tokens.add(t)
            continue
        chars = [c for c in t if "\u4e00" <= c <= "\u9fff"]
        if not chars:
            continue
        if 2 <= len(chars) <= 8:
            tokens.add("".join(chars))
        for i in range(len(chars) - 1):
            tokens.add(chars[i] + chars[i + 1])
    return tokens


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []

    # FAQ / absorb notes: keep 【相关问题】+【参考回答】together. Character windows
    # otherwise cut the answer into a later chunk while the question header
    # ranks #1 and fallback/LLM see metadata without addresses.
    if "【相关问题】" in text or "【参考回答" in text:
        blocks = re.split(r"(?=\n【相关问题】)", text)
        pieces: list[str] = []
        preamble = ""
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            # Title/meta before the first 【相关问题】 → merge into next FAQ block
            if "【相关问题】" not in block and "【参考回答" not in block:
                preamble = f"{preamble}\n\n{block}".strip() if preamble else block
                continue
            if preamble:
                block = f"{preamble}\n\n{block}".strip()
                preamble = ""
            # Single FAQ entry: allow larger than chunk_size (typical learned note)
            if len(block) <= max(chunk_size * 4, 3200):
                pieces.append(block)
            else:
                pieces.extend(_split_text_window(block, chunk_size, overlap))
        if preamble and not pieces:
            pieces.append(preamble)
        return pieces or _split_text_window(text, chunk_size, overlap)

    return _split_text_window(text, chunk_size, overlap)


def _split_text_window(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def _load_csv_rows(path: Path) -> list[Chunk]:
    """Load structured FAQ rows from knowledge base CSV."""
    chunks: list[Chunk] = []
    rel = path.name
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = (row.get("分类") or "").strip()
            q_zh = (row.get("问题（中文）") or "").strip()
            q_en = (row.get("问题（EN）") or "").strip()
            a_zh = (row.get("答案（中文）") or "").strip()
            a_en = (row.get("答案（EN）") or "").strip()
            keywords = (row.get("关键词") or "").strip()
            source_link = (row.get("来源链接") or "").strip()
            row_id = (row.get("编号") or "").strip()

            if not a_zh and not a_en:
                continue

            text = (
                f"【分类】{category}\n"
                f"【编号】{row_id}\n"
                f"【相关问题】{q_zh} / {q_en}\n"
                f"【关键词】{keywords}\n"
                f"【参考回答-中文】{a_zh}\n"
                f"【参考回答-英文】{a_en}\n"
                f"【来源】{source_link}"
            )
            q_blob = f"{q_zh} {q_en}"
            # Keep source URLs in the searchable blob so doc/help links stay retrievable
            chunks.append(
                Chunk(
                    source=f"{rel}#{row_id}",
                    text=text,
                    tokens=_search_tokens(
                        f"{category} {q_zh} {q_en} {keywords} {a_zh} {a_en} {source_link}"
                    ),
                    category=category,
                    question_tokens=_search_tokens(q_blob),
                    keyword_tokens=_search_tokens(keywords),
                )
            )
    return chunks


def _source_excluded(source: str) -> bool:
    name = source.split("#", 1)[0]
    base = Path(name).name
    return any(base.startswith(p) or name.startswith(p) for p in EXCLUDE_SOURCE_PREFIXES)


class KnowledgeBase:
    def __init__(self, directory: Path, chunk_size: int, chunk_overlap: int) -> None:
        self.directory = directory
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._chunks: list[Chunk] = []

    def reload(self) -> int:
        self._chunks = []
        if not self.directory.exists():
            logger.warning("Knowledge directory missing: %s", self.directory)
            return 0

        for path in sorted(self.directory.rglob("*")):
            if path.name == "README.md":
                continue
            suffix = path.suffix.lower()
            try:
                if suffix == ".csv":
                    self._chunks.extend(_load_csv_rows(path))
                elif suffix in {".md", ".txt"}:
                    text = path.read_text(encoding="utf-8")
                    rel = str(path.relative_to(self.directory))
                    if _source_excluded(rel):
                        logger.info("Skip internal doc for FAQ retrieval: %s", rel)
                        continue
                    for piece in _split_text(text, self.chunk_size, self.chunk_overlap):
                        related = ""
                        m = RELATED_RE.search(piece)
                        if m:
                            related = m.group(1)
                        kws = ""
                        mk = KEYWORDS_RE.search(piece)
                        if mk:
                            kws = mk.group(1)
                        self._chunks.append(
                            Chunk(
                                source=rel,
                                text=piece,
                                tokens=_search_tokens(piece),
                                question_tokens=_search_tokens(related),
                                keyword_tokens=_search_tokens(kws),
                            )
                        )
            except OSError as exc:
                logger.warning("Skip %s: %s", path, exc)

        logger.info("Loaded %d knowledge chunk(s) from %s", len(self._chunks), self.directory)
        return len(self._chunks)

    def search(self, query: str, top_k: int = 4) -> list[SearchHit]:
        q_tokens = _search_tokens(query)
        if not q_tokens or not self._chunks:
            return []
        q_expanded = _expand_synonyms(q_tokens)
        must_terms = _required_topic_terms(query)

        hits: list[SearchHit] = []
        q_lower = query.lower().strip()
        for chunk in self._chunks:
            if _source_excluded(chunk.source) or not chunk.tokens:
                continue

            # Soft filter: skip chunks missing required product/topic anchors
            if must_terms and not all(_chunk_mentions(chunk, t) for t in must_terms):
                continue

            q_overlap = q_expanded & (chunk.question_tokens or set())
            kw_overlap = q_expanded & (chunk.keyword_tokens or set())
            body_overlap = q_expanded & chunk.tokens
            if not (q_overlap or kw_overlap or body_overlap):
                continue

            denom = max(len(q_tokens), 1)
            # Free-form learned notes often lack 【相关问题】; weight body higher
            # so absorb → re-ask does not die under min_relevance_score.
            is_learned = chunk.source.startswith("learned/") or "/learned/" in (
                chunk.source.replace("\\", "/")
            )
            body_w = 0.45 if (is_learned and not chunk.question_tokens) else 0.20
            q_w = 0.45 if (is_learned and not chunk.question_tokens) else 0.55
            kw_w = 0.10 if (is_learned and not chunk.question_tokens) else 0.25
            score = (
                q_w * (len(q_overlap) / denom)
                + kw_w * (len(kw_overlap) / denom)
                + body_w * (len(body_overlap) / denom)
            )
            # Distinctive ASCII keyword hits (rpc, sdk, bdex…) — skip stopwords
            # and cap so long English questions cannot saturate every FAQ to 1.0.
            ascii_hits = 0
            blob_lower = chunk.text.lower()
            for t in q_tokens:
                if (
                    t.isascii()
                    and len(t) >= 3
                    and t not in _ASCII_STOP
                    and t in blob_lower
                ):
                    ascii_hits += 1
            if ascii_hits:
                score += min(0.18 * ascii_hits, 0.40)
            if q_lower and q_lower[:48] in blob_lower:
                score += 0.15
            if "【相关问题】" in chunk.text and q_overlap:
                score += 0.12
            # Learned answer body that shares contentful CJK/English terms
            if is_learned and body_overlap:
                contentful = {
                    t
                    for t in q_tokens
                    if t not in {"怎么", "如何", "怎样", "什么", "吗", "呢", "啊"}
                    and t not in _ASCII_STOP
                    and (len(t) >= 2)
                }
                hit_c = contentful & body_overlap
                if hit_c and contentful:
                    score += 0.35 * (len(hit_c) / max(len(contentful), 1))

            # Do not hard-cap at 1.0: uncapped relative order matters when many
            # chunks share generic tokens (mainnet / contract / addresses…).
            hits.append(SearchHit(chunk=chunk, score=score))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)
