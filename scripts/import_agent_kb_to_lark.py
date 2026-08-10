#!/usr/bin/env python3
"""Import local Agent knowledge into the Lark Agent glossary table (deduped)."""

from __future__ import annotations

import argparse
import csv
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
    learned_markdown_to_entry,
)
from bot.lark_bitable import (  # noqa: E402
    batch_create_records,
    batch_delete_records,
    get_tenant_access_token,
    list_records,
)

DEFAULT_APP = "Kb6rbLenJa4FzWsi6pzlTkdjg0e"
DEFAULT_TABLE = "tblP28CyWdY5ml8r"

# Prefer these sources when topics collide (lower = higher priority).
SOURCE_RANK = {
    "bd_faq_batch1.csv": 0,
    "delivery_integration_guide.csv": 1,
    "delivery_project_integration_guide_zh_en.md": 2,
    "delivery_official_website_zh_en.md": 3,
    "delivery_help_center_zh.md": 4,
    "delivery_help_center_en.md": 5,
    "delivery_dev_docs_crawl.md": 6,
    "help_center": 7,
    "learned": 8,
}

# Files never imported into Agent KB (internal / samples).
SKIP_KB_FILES = {
    "README.md",
    "faq.sample.md",
}

TOPIC_RULES: list[tuple[str, list[str]]] = [
    ("mainnet_params", ["chain id", "677", "手动添加", "mainnet parameters", "添加主网", "网络参数"]),
    ("rpc", ["example.com", "官方 rpc", "rpc url", "rpc 地址"]),
    ("explorer", ["example.com", "区块浏览器", "explorer"]),
    ("wss", ["wss://", "websocket", "ws-rpc"]),
    ("wallet_list", ["bitget wallet", "tokenpocket", "okx wallet", "metamask", "列出哪些钱包"]),
    ("integration_flow", ["接入", "integration flow", "标准步骤", "开始接入"]),
    ("bridge", ["example.com", "跨链桥", "bot bridge"]),
    ("dex", ["example.com", "bdex", "swap"]),
    ("universal_router", ["universal router"]),
    ("bundler", ["bundler", "erc-4337", "4337"]),
    ("audit", ["审计", "certik", "audit"]),
    ("faucet", ["faucet", "测试币", "tbot"]),
    ("price_api", ["price api", "价格 api"]),
    ("official_links", ["官方链接", "official links", "linktree"]),
    ("grant_positioning", ["生态扶持计划怎么解释", "ecosystem support program", "grant / 生态扶持"]),
    ("grant_eligible", ["哪些项目适合申请生态扶持", "eligible"]),
    ("grant_tiers", ["grant 档位", "grant tiers"]),
    ("bo_wallet", ["bo wallet", "example.com"]),
]


HELP_CENTER_ENTRIES: list[AgentKbEntry] = [
    AgentKbEntry(
        "HC-001",
        "Help Center / Getting Started",
        "如何把 Delivery Agent 主网加到钱包？",
        "主网参数：Network Name `Delivery Agent`；RPC `https://example.com ID `677`；Symbol `BOT`；Explorer `https://example.com"
        "MetaMask / TokenPocket 都可按上述参数手动添加；也可用 Chainlist 搜索 Delivery Agent 后核对 Chain ID=677。\n"
        "加完后切到主网，在浏览器核对地址。文档：https://example.com",
        "加链;MetaMask;TokenPocket;677;RPC",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-002",
        "Help Center / Getting Started",
        "主网 Gas（BOT）怎么准备？",
        "主网交易需要原生币 BOT 作 Gas。可通过官方 Bridge `https://example.com 跨入，并在钱包或 `https://example.com 确认到账。\n"
        "测试网资产不能付主网 Gas。不要接受私聊“代充 Gas / 先转账”一类请求。",
        "Gas;BOT;bridge",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-003",
        "Help Center / Wallet",
        "如何创建 / 下载 BO Wallet？",
        "只从官网入口下载：`https://example.com PIN，离线备份助记词，并完成助记词校验。\n"
        "不要截图/上传助记词，不要把助记词或私钥发给任何人（含“客服/管理员”）。",
        "BO Wallet;创建钱包;助记词",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-004",
        "Help Center / Wallet",
        "如何导入或恢复 BO Wallet？",
        "在 BO Wallet 选择导入钱包，用助记词或私钥恢复，再设置本机 PIN。恢复后核对地址是否与原地址一致，并切换到 Delivery Agent 查看资产。\n"
        "余额为 0 时，先查网络是否选对、助记词顺序、地址是否匹配。",
        "导入;恢复;助记词",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-005",
        "Help Center / Wallet",
        "BO Wallet 里如何管理多个钱包 / 转账？",
        "可在钱包管理中切换、重命名、添加或移除钱包；高风险操作前先确认备份。\n"
        "转账时核对网络=Delivery Agent、收款地址、代币合约与金额；大额前先小额测试。浏览器：`https://example.com",
        "转账;多钱包;管理",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-006",
        "Help Center / Explorer",
        "如何用浏览器查地址和交易？",
        "打开 `https://example.com TxHash，核对 From/To、Token Transfers、状态与时间。\n"
        "官方客服只能协助解读公开链上信息，不能代签、代恢复钱包或保证追回资产。",
        "explorer;scan;交易查询",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-007",
        "Help Center / Bridge",
        "如何用 BOT Bridge 跨链到 Delivery Agent？跨链未到账怎么办？",
        "入口：`https://example.com Delivery Agent，确认金额与费用后再提交。\n"
        "未到账：先用源链和 Delivery Agent 浏览器核对 Tx 状态与目标地址；保留 TxHash。不要反复重提，不要点私聊“加速/退款”链接。",
        "Bridge;跨链;未到账",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-008",
        "Help Center / DEX",
        "如何在 BDEX 兑换 USDT / BOT？",
        "入口：`https://example.com Delivery Agent，选择交易对、滑点与授权后再兑换。\n"
        "DEX 文档：https://example.com （中文：/zh-Hans/docs/DEX/）",
        "BDEX;swap;兑换",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-009",
        "Help Center / Multisig",
        "如何在 Delivery Agent 上创建 Safe 多签？",
        "可按 Help Center「Create a Safe Multisig Account on Delivery Agent」流程在 Delivery Agent 上创建 Safe 多签账户。\n"
        "创建前确认网络为 Delivery Agent（Chain ID 677），并保留 owners / threshold 配置记录。Help Center：https://example.com",
        "Safe;多签;multisig",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-010",
        "Help Center / Security",
        "官方链接与防骗要点是什么？",
        "只用官方域名与入口（官网、钱包、Bridge、DEX、Explorer、开发者文档）。\n"
        "不要点私聊空投/客服链接；不要分享助记词/私钥/验证码；合约地址以官方文档或浏览器已验证页面为准。\n"
        "Help Center 防骗指南：https://example.com",
        "防骗;官方链接;安全",
        "https://example.com",
    ),
    AgentKbEntry(
        "HC-011",
        "Help Center / Security",
        "发错资产 / 钱包应急怎么办？",
        "先停手：不要继续按陌生指引转账。用浏览器核对 Tx 是否已成功、收款地址是否错误。\n"
        "官方支持可协助解读公开链上记录，但不能改写链上结果、代签或保证追回。若设备泄露，立即转移剩余资产并轮换密钥（在安全环境下）。",
        "发错;应急;安全",
        "https://example.com",
    ),
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _topic_key(question: str, answer: str, keywords: str = "") -> str | None:
    blob = _norm(f"{question} {answer} {keywords}")
    for key, needles in TOPIC_RULES:
        if any(n in blob for n in needles):
            return key
    return None


def _is_old_robotics_row(source: str, category: str, answer: str) -> bool:
    blob = f"{source} {category} {answer}".lower()
    if "delivery.gitbook.io" in blob or "delivery.dev" in blob:
        return True
    if "$bcn" in blob:
        return True
    return False


def _load_csv_entries(
    path: Path, *, include_old_robotics: bool = False
) -> list[tuple[str, AgentKbEntry, str | None]]:
    out: list[tuple[str, AgentKbEntry, str | None]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            entry_id = (row.get("编号") or "").strip()
            category = (row.get("分类") or "").strip()
            q = (row.get("问题（中文）") or "").strip()
            a = (row.get("答案（中文）") or "").strip()
            if not a and not q:
                continue
            source = (row.get("来源链接") or "").strip()
            if (
                not include_old_robotics
                and path.name == "delivery_knowledge_base.csv"
                and _is_old_robotics_row(source, category, a)
            ):
                continue
            if not entry_id:
                entry_id = f"KB-{path.stem}-{len(out)+1}"
            # Prefix colliding numeric IDs from knowledge_base
            if path.name == "delivery_knowledge_base.csv" and entry_id.isdigit():
                entry_id = f"KB-{entry_id}"
            keywords = (row.get("关键词") or "").strip()
            topic = _topic_key(q, a, keywords)
            entry = AgentKbEntry(
                entry_id=entry_id,
                category=category or path.stem,
                question=q or entry_id,
                answer=a,
                keywords=keywords,
                source=source or path.name,
                updated_at=datetime.now().isoformat(timespec="seconds"),
            )
            out.append((path.name, entry, topic))
    return out


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Return (title, body) sections. Prefer --- page breaks; else ## headings."""
    text = text or ""
    out: list[tuple[str, str]] = []
    if re.search(r"(?m)^---\s*$", text):
        parts = re.split(r"(?m)^---\s*$", text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            m = re.search(r"(?m)^##\s+(.+)$", part)
            if not m:
                continue
            title = m.group(1).strip()
            body = part[m.end() :].strip()
            if len(body) < 20:
                continue
            out.append((title, body))
        if out:
            return out

    parts = re.split(r"(?m)^##\s+", text)
    for part in parts[1:]:
        lines = part.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if len(body) < 20:
            continue
        out.append((title, body))
    return out


def _parse_labeled_body(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for m in re.finditer(
        r"【(相关问题|关键词|参考回答(?:-中文|-英文)?|参考回答|来源)】\s*(.*?)(?=\n【|\Z)",
        body or "",
        re.DOTALL,
    ):
        key, val = m.group(1), m.group(2).strip()
        if key == "相关问题":
            fields["question"] = val
        elif key == "关键词":
            fields["keywords"] = val
        elif key == "来源":
            fields["source"] = val
        elif key.endswith("-英文"):
            fields["answer_en"] = val
        else:
            fields["answer_zh"] = val
    return fields


def _compose_bilingual_answer(zh: str, en: str) -> str:
    zh, en = (zh or "").strip(), (en or "").strip()
    if zh and en:
        return f"{zh}\n\n---\n\n[EN]\n{en}"
    return zh or en


def _load_markdown_doc(
    path: Path,
    *,
    id_prefix: str,
    category: str,
    default_source: str,
    prefer_labeled: bool = False,
) -> list[tuple[str, AgentKbEntry, str | None]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    sections = _split_markdown_sections(text)
    out: list[tuple[str, AgentKbEntry, str | None]] = []
    for idx, (title, body) in enumerate(sections, start=1):
        labeled = _parse_labeled_body(body) if prefer_labeled or "【参考回答" in body else {}
        src_m = re.search(r"(?im)^Source:\s*(\S+)", body)
        source = (
            labeled.get("source")
            or (src_m.group(1) if src_m else "")
            or default_source
            or path.name
        )
        if labeled.get("answer_zh") or labeled.get("answer_en"):
            answer = _compose_bilingual_answer(
                labeled.get("answer_zh", ""), labeled.get("answer_en", "")
            )
            question = (labeled.get("question") or title).strip()
            # Use first question line if multi-line related questions
            if "\n" in question:
                question = question.splitlines()[0].strip()
            if " / " in question:
                question = question.split(" / ", 1)[0].strip()
            keywords = labeled.get("keywords") or ""
        else:
            answer = body
            question = title
            keywords = ""
        if not answer.strip():
            continue
        if len(answer) > 3500:
            answer = answer[:3497] + "…"
        entry = AgentKbEntry(
            entry_id=f"{id_prefix}-{idx:03d}",
            category=category,
            question=question[:2000],
            answer=answer,
            keywords=keywords,
            source=source,
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )
        out.append((path.name, entry, _topic_key(question, answer, keywords)))
    return out


def _load_learned_entries(learned_dir: Path) -> list[tuple[str, AgentKbEntry, str | None]]:
    out: list[tuple[str, AgentKbEntry, str | None]] = []
    if not learned_dir.exists():
        return out
    for path in sorted(learned_dir.glob("learned_*.md")):
        body = path.read_text(encoding="utf-8", errors="ignore")
        entry = learned_markdown_to_entry(path.name, body)
        if not entry.answer.strip():
            continue
        topic = _topic_key(entry.question, entry.answer, entry.keywords)
        out.append(("learned", entry, topic))
    return out


def _is_internal_lark_doc(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith("lark_") or "内部" in name or "sop" in name


def build_entries(knowledge_dir: Path, *, full: bool = False) -> list[AgentKbEntry]:
    bags: list[tuple[str, AgentKbEntry, str | None]] = []
    for name in (
        "bd_faq_batch1.csv",
        "delivery_integration_guide.csv",
        "delivery_knowledge_base.csv",
    ):
        path = knowledge_dir / name
        if path.exists():
            bags.extend(_load_csv_entries(path, include_old_robotics=full))

    if full:
        bags.extend(
            _load_markdown_doc(
                knowledge_dir / "delivery_help_center_zh.md",
                id_prefix="HC-ZH",
                category="Help Center / ZH",
                default_source="https://example.com",
            )
        )
        bags.extend(
            _load_markdown_doc(
                knowledge_dir / "delivery_help_center_en.md",
                id_prefix="HC-EN",
                category="Help Center / EN",
                default_source="https://example.com",
            )
        )
        bags.extend(
            _load_markdown_doc(
                knowledge_dir / "delivery_dev_docs_crawl.md",
                id_prefix="DEVDOC",
                category="Developer Docs",
                default_source="https://example.com",
            )
        )
        bags.extend(
            _load_markdown_doc(
                knowledge_dir / "delivery_official_website_zh_en.md",
                id_prefix="WEB",
                category="Official Website",
                default_source="https://example.com",
                prefer_labeled=True,
            )
        )
        bags.extend(
            _load_markdown_doc(
                knowledge_dir / "delivery_project_integration_guide_zh_en.md",
                id_prefix="INTG-MD",
                category="Project Integration Guide",
                default_source="Delivery Agent Project Integration Guide",
                prefer_labeled=True,
            )
        )
        # Any other public .md not already covered (skip samples / internal Lark)
        known = {
            "delivery_help_center_zh.md",
            "delivery_help_center_en.md",
            "delivery_dev_docs_crawl.md",
            "delivery_official_website_zh_en.md",
            "delivery_project_integration_guide_zh_en.md",
        }
        for path in sorted(knowledge_dir.glob("*.md")):
            if path.name in SKIP_KB_FILES or path.name in known or _is_internal_lark_doc(path):
                continue
            bags.extend(
                _load_markdown_doc(
                    path,
                    id_prefix=f"MD-{path.stem[:20]}",
                    category=path.stem,
                    default_source=path.name,
                    prefer_labeled=True,
                )
            )
    else:
        for hc in HELP_CENTER_ENTRIES:
            bags.append(("help_center", hc, _topic_key(hc.question, hc.answer, hc.keywords)))

    bags.extend(_load_learned_entries(knowledge_dir / "learned"))

    if full:
        # Full import: keep all rows; only avoid duplicate entry_id
        final: list[AgentKbEntry] = []
        seen: set[str] = set()
        for _, entry, _ in bags:
            eid = entry.entry_id
            if eid in seen:
                n = 2
                while f"{entry.entry_id}-{n}" in seen:
                    n += 1
                entry.entry_id = f"{entry.entry_id}-{n}"
            seen.add(entry.entry_id)
            final.append(entry)
        print(f"Built {len(final)} entries (full import, no topic dedupe; raw={len(bags)})")
        return final

    # Dedup by topic: keep highest-priority source; also dedup exact entry_id.
    by_topic: dict[str, tuple[int, AgentKbEntry]] = {}
    by_id: dict[str, AgentKbEntry] = {}
    dropped_topic = 0
    for source_name, entry, topic in bags:
        rank = SOURCE_RANK.get(source_name, 9)
        if topic:
            prev = by_topic.get(topic)
            if prev and prev[0] <= rank:
                dropped_topic += 1
                continue
            by_topic[topic] = (rank, entry)
            if prev:
                by_id.pop(prev[1].entry_id, None)
        if entry.entry_id in by_id:
            continue
        by_id[entry.entry_id] = entry

    winners = {e.entry_id for _, e in by_topic.values()}
    final = []
    seen = set()
    for source_name, entry, topic in bags:
        if entry.entry_id in seen:
            continue
        if topic and entry.entry_id not in winners:
            continue
        if entry.entry_id not in by_id:
            continue
        final.append(by_id[entry.entry_id])
        seen.add(entry.entry_id)

    print(
        f"Built {len(final)} entries "
        f"(from {len(bags)} raw; topic-deduped ~{dropped_topic})"
    )
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-token", default=DEFAULT_APP)
    parser.add_argument("--table-id", default=DEFAULT_TABLE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-existing", action="store_true")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Import all CSV + help/docs/website/integration MD + learned; no topic dedupe",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    import os

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("Missing LARK_APP_ID / LARK_APP_SECRET")
        return 1

    entries = build_entries(ROOT / "knowledge", full=args.full)
    if args.dry_run:
        cats: dict[str, int] = {}
        for e in entries:
            cats[e.category] = cats.get(e.category, 0) + 1
        for c, n in sorted(cats.items(), key=lambda x: -x[1])[:30]:
            print(f"  [{n}] {c}")
        print("sample:")
        for e in entries[:8]:
            print(f"  {e.entry_id}: {e.question[:60]}")
        return 0

    token = get_tenant_access_token(app_id, app_secret)
    created_fields = ensure_agent_kb_fields(token, args.app_token, args.table_id)
    if created_fields:
        print("Created fields:", ", ".join(created_fields))
        time.sleep(1)

    if not args.keep_existing:
        existing = list_records(token, args.app_token, args.table_id)
        ids = [str(r.get("record_id") or r.get("id") or "") for r in existing]
        ids = [i for i in ids if i]
        if ids:
            n = batch_delete_records(token, args.app_token, args.table_id, ids)
            print(f"Deleted {n} existing records")
            time.sleep(1)

    payload = [e.to_lark_fields() for e in entries]
    for fields in payload:
        assert PRIMARY_FIELD in fields
        for name in EXTRA_FIELDS:
            fields.setdefault(name, "")

    created = batch_create_records(token, args.app_token, args.table_id, payload)
    print(f"Created {created} records in table {args.table_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
