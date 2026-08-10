#!/usr/bin/env python3
"""Sync knowledge into Lark Agent KB as readable, matched Q/A (not bot window-chunks)."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.agent_kb_sync import (  # noqa: E402
    EXTRA_FIELDS,
    PRIMARY_FIELD,
    AgentKbEntry,
    ensure_agent_kb_fields,
)
from bot.lark_bitable import (  # noqa: E402
    batch_create_records,
    batch_delete_records,
    get_tenant_access_token,
    list_records,
)

DEFAULT_APP = "Kb6rbLenJa4FzWsi6pzlTkdjg0e"
DEFAULT_TABLE = "tblP28CyWdY5ml8r"
MAX_ANSWER = 3400

SKIP_NAMES = {"README.md", "faq.sample.md"}

HELP_NAV = {
    "CTRL K",
    "入门指南",
    "钱包与账户",
    "网络与交易",
    "跨链与 DeFi",
    "项目工具",
    "安全与帮助",
    "Getting Started",
    "Wallet & Accounts",
    "Network & Transactions",
    "Bridge & DeFi",
    "Project Tools",
    "Security & Help",
    "在 MetaMask 添加 Delivery Agent Mainnet",
    "在 TokenPocket 添加 Delivery Agent Mainnet",
    "获取 BOT 作为 Delivery Agent Gas",
    "创建 BO Wallet 钱包",
    "下载和安装 BO Wallet",
    "导入或恢复 BO Wallet",
    "管理 BO Wallet 中的钱包",
    "在 BO Wallet 发送资产",
    "使用 Delivery Agent Explorer 查询地址和交易",
    "BOT Bridge 跨链未到账怎么办",
    "使用 BOT Bridge 跨入 Delivery Agent",
    "在 B DEX 兑换 USDT 或 BOT",
    "使用 Safe 创建 Delivery Agent 多签账户",
    "Delivery Agent 官方链接与防诈骗指南",
    "钱包安全与异常处理指南",
    "资产转错后的处理指南",
    "Add Delivery Agent Mainnet to MetaMask",
    "Add Delivery Agent Mainnet to TokenPocket",
    "Get BOT for Delivery Agent Gas",
    "Create a BO Wallet",
    "Download and Install BO Wallet",
    "Import or Recover a BO Wallet",
    "Manage Wallets in BO Wallet",
    "Send Assets in BO Wallet",
    "Use Delivery Agent Explorer to Check Addresses and Transactions",
    "What to Do If a BOT Bridge Transfer Has Not Arrived",
    "Bridge Assets to Delivery Agent with BOT Bridge",
    "Swap USDT or BOT on B DEX",
    "Create a Safe Multisig Account on Delivery Agent",
    "Delivery Agent Official Links and Anti-Scam Guide",
    "Wallet Security and Emergency Response Guide",
    "What to Do If You Sent Assets to the Wrong Address",
}

FIELD_RE = re.compile(
    r"【(相关问题|关键词|参考回答(?:-中文|-英文)?|参考回答|来源)】\s*(.*?)(?=\n【|\Z)",
    re.DOTALL,
)


def _parse_fields(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in FIELD_RE.finditer(block or ""):
        key, val = m.group(1), m.group(2).strip()
        if key == "相关问题":
            out["question"] = val
        elif key == "关键词":
            out["keywords"] = val
        elif key == "来源":
            out["source"] = val
        elif key.endswith("-英文"):
            out["en"] = val
        else:
            out["zh"] = val
    return out


def _primary_question(raw: str) -> str:
    q = (raw or "").strip()
    if not q:
        return ""
    q = q.splitlines()[0].strip()
    # Prefer Chinese side before " / "
    if " / " in q:
        q = q.split(" / ", 1)[0].strip()
    return q[:200]


def _fit_answer(answer: str, source_url: str = "") -> str:
    answer = (answer or "").strip()
    if len(answer) <= MAX_ANSWER:
        return answer
    suffix = "\n\n（内容较长，已截断）"
    if source_url:
        # keep source short
        src = source_url.splitlines()[0].strip()
        if " | " in src:
            src = src.split(" | ", 1)[0].strip()
        suffix += f"\n全文：{src}"
    budget = MAX_ANSWER - len(suffix) - 8
    window = answer[:budget]
    cut = max(
        window.rfind("\n- "),
        window.rfind("\n\n"),
        window.rfind("\n"),
        window.rfind("。"),
        window.rfind(". "),
        window.rfind("！"),
        window.rfind("？"),
    )
    if cut < budget * 0.4:
        cut = budget
    trimmed = window[:cut].rstrip(" -\t")
    return trimmed + suffix


def _clean_help_body(title: str, body: str) -> tuple[str, str]:
    src = ""
    m = re.search(r"(?im)^Source:\s*(\S+)", body)
    if m:
        src = m.group(1).strip()
    raw_lines = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("Source:")]
    # Find real content start (skip duplicated sidebar menus)
    start_idx = None
    for i, line in enumerate(raw_lines):
        if line in HELP_NAV or line == title or line == "CTRL K":
            continue
        if (
            re.match(r"^STEP\s*\d+", line, re.I)
            or "主网参数" in line
            or "Mainnet Parameters" in line
            or line.startswith("Field ")
            or line.startswith("项目 ")
            or line.startswith("Network Name")
            or line.startswith("RPC URL")
        ):
            start_idx = i
            break
    if start_idx is None:
        # fallback: first non-nav line with enough substance
        for i, line in enumerate(raw_lines):
            if line in HELP_NAV or line == title or line == "CTRL K":
                continue
            if len(line) >= 48:
                start_idx = i
                break
    if start_idx is None:
        return src, ""

    lines: list[str] = []
    for line in raw_lines[start_idx:]:
        if line == "CTRL K":
            continue
        # Stop when sidebar/next-article title appears after content started
        if line in HELP_NAV and line != title:
            break
        if line == title and lines:
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    return src, text


def _clean_docs_body(title: str, body: str) -> tuple[str, str]:
    src = ""
    m = re.search(r"(?im)^Source:\s*(\S+)", body)
    if m:
        src = m.group(1).strip()
    lines = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("Source:"):
            continue
        if line in {title, "Bridge", "DEX", "Developers", "开发者"} and not lines:
            continue
        # docusaurus emoji catalogue noise
        if line.startswith("📄️") and len(line) < 80:
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    # light table readability: insert spaces between camel boundaries rarely helpful;
    # keep as-is but ensure not empty
    return src, text


def _clean_blog_body(title: str, body: str) -> str:
    text = body
    text = re.sub(r"^返回博客.*?\n", "", text)
    text = re.sub(r"复制链接分享\n?", "", text)
    text = re.sub(r"(上一篇|下一篇).*$", "", text, flags=re.S)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # drop leading title duplicate
    if text.startswith(title):
        text = text[len(title) :].lstrip()
    return text


def _iter_labeled_entries(text: str) -> list[dict[str, str]]:
    parts = re.split(r"(?=【相关问题】)", text or "")
    out = []
    for part in parts:
        if "【相关问题】" not in part:
            continue
        fields = _parse_fields(part)
        q = _primary_question(fields.get("question", ""))
        zh = (fields.get("zh") or "").strip()
        en = (fields.get("en") or "").strip()
        # Drop placeholder "EN" sides that are just "see original"
        if en and (
            len(en) < 40
            or en.startswith(("详见", "原文见", "See:", "See ", "全文"))
        ):
            en = ""
        if not q or (not zh and not en):
            continue
        if zh and en:
            combo = f"{zh}\n\n[EN]\n{en}"
            # Prefer complete Chinese over mid-cut bilingual blobs
            if len(combo) > MAX_ANSWER and len(zh) <= MAX_ANSWER:
                answer = f"{zh}\n\n[EN] See source for English version."
            else:
                answer = combo
        else:
            answer = zh or en
        source = (fields.get("source") or "").strip().splitlines()[0].strip()
        # Guard against 来源 field swallowing following markdown headers
        if "【" in source:
            source = source.split("【", 1)[0].strip()
        if "\n## " in source or source.startswith("## "):
            source = source.split("## ", 1)[0].strip()
        out.append(
            {
                "question": q,
                "answer": answer,
                "keywords": fields.get("keywords", ""),
                "source": source,
            }
        )
    return out


def _split_md_sections(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if re.search(r"(?m)^---\s*$", text):
        for part in re.split(r"(?m)^---\s*$", text):
            part = part.strip()
            if not part:
                continue
            m = re.search(r"(?m)^##\s+(.+)$", part)
            if not m:
                continue
            title = m.group(1).strip()
            body = part[m.end() :].strip()
            if body:
                out.append((title, body))
        if out:
            return out
    parts = re.split(r"(?m)^##\s+", text)
    for part in parts[1:]:
        lines = part.strip().splitlines()
        if not lines:
            continue
        out.append((lines[0].strip(), "\n".join(lines[1:]).strip()))
    return out


class Builder:
    def __init__(self) -> None:
        self.entries: list[AgentKbEntry] = []
        self.now = datetime.now().isoformat(timespec="seconds")
        self._seen: set[str] = set()

    def add(
        self,
        entry_id: str,
        category: str,
        question: str,
        answer: str,
        keywords: str = "",
        source: str = "",
    ) -> None:
        question = (question or "").strip()
        answer = _fit_answer(answer, source)
        if not question or not answer or len(answer) < 20:
            return
        # reject obvious Q/A identity garbage for learned
        if question == answer and len(question) > 180:
            question = question[:120] + "…"
        eid = entry_id
        if eid in self._seen:
            n = 2
            while f"{entry_id}-{n}" in self._seen:
                n += 1
            eid = f"{entry_id}-{n}"
        self._seen.add(eid)
        self.entries.append(
            AgentKbEntry(
                entry_id=eid[:80],
                category=(category or "General")[:200],
                question=question[:2000],
                answer=answer,
                keywords=(keywords or "")[:500],
                source=(source or "")[:500],
                updated_at=self.now,
            )
        )


def build_entries(kb_dir: Path) -> list[AgentKbEntry]:
    b = Builder()

    # 1) CSV FAQ — gold standard matched pairs
    for path in sorted(kb_dir.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                eid = (row.get("编号") or "").strip()
                if not eid:
                    continue
                q = (row.get("问题（中文）") or "").strip()
                q_en = (row.get("问题（EN）") or "").strip()
                a_zh = (row.get("答案（中文）") or "").strip()
                a_en = (row.get("答案（EN）") or "").strip()
                if not a_zh and not a_en:
                    continue
                question = q or q_en
                answer = a_zh if a_zh else a_en
                if a_zh and a_en:
                    answer = f"{a_zh}\n\n[EN]\n{a_en}"
                b.add(
                    eid,
                    (row.get("分类") or path.stem).strip(),
                    question,
                    answer,
                    (row.get("关键词") or "").strip(),
                    (row.get("来源链接") or path.name).strip(),
                )

    # 2) Markdown
    for path in sorted(kb_dir.rglob("*.md")):
        if path.name in SKIP_NAMES or path.name.startswith("lark_"):
            continue
        if path.parent.name == "learned":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(kb_dir))
        stem = path.stem

        # Prefer explicit labeled FAQ blocks anywhere in file
        # Help center / docs / blogs: dedicated cleaners (ignore noisy labels if any)
        if stem.startswith("delivery_help_center"):
            lang = "ZH" if stem.endswith("_zh") else "EN"
            for i, (title, body) in enumerate(_split_md_sections(text), start=1):
                src, cleaned = _clean_help_body(title, body)
                if len(cleaned) < 80:
                    continue
                b.add(
                    f"HC-{lang}-{i:03d}",
                    f"Help Center / {lang}",
                    title,
                    cleaned,
                    "help center",
                    src or rel,
                )
            continue

        if stem == "delivery_dev_docs_crawl":
            for i, (title, body) in enumerate(_split_md_sections(text), start=1):
                if title.lower().startswith("developer docs"):
                    continue
                src, cleaned = _clean_docs_body(title, body)
                if len(cleaned) < 40:
                    continue
                question = f"文档：{title}"
                if src:
                    cleaned = f"{cleaned}\n\n来源：{src}"
                b.add(
                    f"DEV-{i:03d}",
                    "Developer Docs",
                    question,
                    cleaned,
                    "dev-docs;documentation",
                    src or rel,
                )
            continue

        if stem == "delivery_official_blog_zh_en":
            for i, (title, body) in enumerate(_split_md_sections(text), start=1):
                if title.startswith("Delivery Agent Official Blog"):
                    continue
                src_m = re.search(r"(?im)^Source:\s*(\S+)", body)
                src = src_m.group(1) if src_m else rel
                # Prefer labeled answer body if present, else raw section
                labeled_one = _iter_labeled_entries(body)
                if labeled_one:
                    cleaned = labeled_one[0]["answer"]
                    title = labeled_one[0]["question"] or title
                    src = labeled_one[0].get("source") or src
                else:
                    cleaned = body
                cleaned = _clean_blog_body(title, cleaned)
                cleaned = re.sub(r"【[^】]+】\s*", "", cleaned)
                cleaned = cleaned.replace("详见原文：", "").replace("原文见：", "").strip()
                # Hard-stop at next post chrome
                cleaned = re.split(r"\n(?=返回博客|上一篇|下一篇|Source:)", cleaned)[0].strip()
                if len(cleaned) < 80:
                    continue
                b.add(
                    f"BLOG-{i:03d}",
                    "Official Blog",
                    title,
                    cleaned,
                    "blog",
                    src,
                )
            continue

        labeled = _iter_labeled_entries(text)
        if labeled:
            for i, item in enumerate(labeled, start=1):
                prefix = {
                    "delivery_complete_faq_builder_guide_zh_en": "CFAQ",
                    "delivery_project_integration_guide_zh_en": "INTG",
                    "delivery_official_website_zh_en": "WEB",
                    "delivery_project_party_zh_en": "ECO",
                    "delivery_news_media": "MEDIA",
                    "delivery_whitepaper_and_chain_audit": "WP",
                }.get(stem, f"LBL-{stem[:12]}")
                answer = item["answer"]
                # Keep only the answer body; strip accidental markdown headers
                answer = re.split(r"\n##\s+", answer)[0].strip()
                b.add(
                    f"{prefix}-{i:03d}",
                    stem.replace("delivery_", "").replace("_", " ")[:80],
                    item["question"],
                    answer,
                    item.get("keywords", ""),
                    item.get("source") or rel,
                )
            continue

        # Other unlabeled md
        for i, (title, body) in enumerate(_split_md_sections(text), start=1):
            if len(body) < 40:
                continue
            if body.lower().startswith("source:") and len(body) < 200:
                continue
            src_m = re.search(r"(?im)^Source:\s*(\S+)", body)
            src = src_m.group(1) if src_m else rel
            b.add(
                f"MD-{stem[:16]}-{i:03d}",
                stem.replace("delivery_", "")[:80],
                f"资料：{title}",
                body,
                "",
                src,
            )

    # 3) Learned — only if structured enough
    learned_dir = kb_dir / "learned"
    if learned_dir.exists():
        for path in sorted(learned_dir.glob("learned_*.md")):
            body = path.read_text(encoding="utf-8", errors="ignore")
            meta = {
                m.group(1).lower(): m.group(2).strip()
                for m in re.finditer(
                    r"<!--\s*(learned_at|chat_id|sender_id|sender|related_question)\s*:\s*(.*?)\s*-->",
                    body,
                    re.I | re.S,
                )
            }
            fields = _parse_fields(re.sub(r"<!--.*?-->", "", body, flags=re.S))
            q = _primary_question(fields.get("question") or meta.get("related_question", ""))
            ans = (fields.get("zh") or fields.get("en") or "").strip()
            if not ans:
                # legacy whole-body answer, but require a short related question
                cleaned = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()
                cleaned = re.sub(r"^#\s*.+\n+", "", cleaned).strip()
                ans = cleaned
            if not q:
                # derive short question from first sentence only if short
                first = ans.splitlines()[0].strip() if ans else ""
                if 8 <= len(first) <= 100:
                    q = first
                else:
                    continue  # skip unusable learned notes
            if len(ans) < 20:
                continue
            stamp = path.name.replace("learned_", "").replace(".md", "")
            b.add(
                f"LEARN-{stamp}",
                "Learned / 自动学习",
                q,
                ans,
                fields.get("keywords") or "learned;absorb",
                f"knowledge/learned/{path.name}",
            )

    return b.entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-token", default=DEFAULT_APP)
    parser.add_argument("--table-id", default=DEFAULT_TABLE)
    parser.add_argument("--knowledge-dir", type=Path, default=ROOT / "knowledge")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    entries = build_entries(args.knowledge_dir)
    print(f"Built {len(entries)} matched Q/A entries from {args.knowledge_dir}")

    # quality report
    bad_q = [e for e in entries if e.question.startswith(("Source", "http", "抓取"))]
    short_a = [e for e in entries if len(e.answer) < 30]
    print(f"quality: bad_questions={len(bad_q)} short_answers={len(short_a)}")
    for e in entries[:8]:
        print(f"  {e.entry_id}: Q={e.question[:50]} | A={e.answer[:60]!r}")

    if args.dry_run:
        return 0

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("Missing LARK_APP_ID / LARK_APP_SECRET")
        return 1

    token = get_tenant_access_token(app_id, app_secret)
    ensure_agent_kb_fields(token, args.app_token, args.table_id)
    existing = list_records(token, args.app_token, args.table_id)
    ids = [str(r.get("record_id") or r.get("id") or "") for r in existing]
    ids = [i for i in ids if i]
    if ids:
        print(f"Deleting {len(ids)} old records...")
        print("Deleted", batch_delete_records(token, args.app_token, args.table_id, ids))
        time.sleep(1)

    payload = [e.to_lark_fields() for e in entries]
    for fields in payload:
        for name in EXTRA_FIELDS:
            fields.setdefault(name, "")
        assert PRIMARY_FIELD in fields

    created = batch_create_records(
        token, args.app_token, args.table_id, payload, batch_size=40
    )
    print(f"Created {created}")
    time.sleep(1)
    print("Verify", len(list_records(token, args.app_token, args.table_id)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
