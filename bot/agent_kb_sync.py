"""Sync absorb/learn entries to the Lark Agent glossary Bitable."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bot.lark_bitable import (
    LarkBitableError,
    create_field,
    create_record,
    get_tenant_access_token,
    list_fields,
    list_records,
    update_record,
)

logger = logging.getLogger(__name__)

PRIMARY_FIELD = "文本"
EXTRA_FIELDS = ("编号", "分类", "问题", "答案", "关键词", "来源", "更新时间")

_META_RE = re.compile(
    r"<!--\s*(learned_at|chat_id|sender_id|sender|related_question)\s*:\s*(.*?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)
_FIELD_RE = re.compile(
    r"【(相关问题|关键词|参考回答(?:-中文|-英文)?|参考回答)】\s*(.*?)(?=\n【|\Z)",
    re.DOTALL,
)


@dataclass
class AgentKbEntry:
    entry_id: str
    category: str
    question: str
    answer: str
    keywords: str = ""
    source: str = ""
    updated_at: str = ""

    def to_lark_fields(self) -> dict[str, Any]:
        # Primary「文本」: prefer Chinese side before the EN question separator,
        # matching BDQA style ("BDQA-001 | BOT Chain 是什么？").
        q_title = self.question.strip()
        m = re.search(
            r"\s+/\s+(?=(?:What|How|Is|Are|Can|Do|Does|Which|Why|When|Where|Who|"
            r"Will|Should|Could|Would)\b)",
            q_title,
        )
        if m:
            left = q_title[: m.start()].strip()
            if left:
                q_title = left
        title = f"{self.entry_id} | {q_title}".strip(" |")
        if len(title) > 200:
            title = title[:197] + "…"
        answer = self.answer.strip()
        if len(answer) > 3500:
            answer = answer[:3497] + "…"
        question = self.question.strip()
        if len(question) > 2000:
            question = question[:1997] + "…"
        return {
            PRIMARY_FIELD: title,
            "编号": self.entry_id,
            "分类": self.category,
            "问题": question,
            "答案": answer,
            "关键词": self.keywords.strip(),
            "来源": self.source.strip(),
            "更新时间": self.updated_at or datetime.now().isoformat(timespec="seconds"),
        }


def ensure_agent_kb_fields(token: str, app_token: str, table_id: str) -> list[str]:
    existing = {str(f.get("field_name") or "") for f in list_fields(token, app_token, table_id)}
    created: list[str] = []
    for name in EXTRA_FIELDS:
        if name in existing:
            continue
        create_field(token, app_token, table_id, name, field_type=1)
        created.append(name)
        existing.add(name)
    return created


def _index_by_entry_id(records: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rec in records:
        rid = str(rec.get("record_id") or rec.get("id") or "")
        fields = rec.get("fields") or {}
        eid = str(fields.get("编号") or "").strip()
        if rid and eid:
            out[eid] = rid
    return out


def upsert_entry_to_lark(
    entry: AgentKbEntry,
    *,
    app_id: str,
    app_secret: str,
    app_token: str,
    table_id: str,
    existing_ids: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Create or update by 编号. Returns (record_id, 'created'|'updated')."""
    token = get_tenant_access_token(app_id, app_secret)
    ensure_agent_kb_fields(token, app_token, table_id)
    fields = entry.to_lark_fields()
    if existing_ids is None:
        existing_ids = _index_by_entry_id(list_records(token, app_token, table_id))
    record_id = existing_ids.get(entry.entry_id)
    if record_id:
        update_record(token, app_token, table_id, record_id, fields)
        return record_id, "updated"
    record_id = create_record(token, app_token, table_id, fields)
    existing_ids[entry.entry_id] = record_id
    return record_id, "created"


def push_entry_to_lark(
    entry: AgentKbEntry,
    *,
    app_id: str,
    app_secret: str,
    app_token: str,
    table_id: str,
) -> str:
    record_id, _ = upsert_entry_to_lark(
        entry,
        app_id=app_id,
        app_secret=app_secret,
        app_token=app_token,
        table_id=table_id,
    )
    return record_id


def _parse_meta(body: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for m in _META_RE.finditer(body or ""):
        meta[m.group(1).lower()] = m.group(2).strip()
    return meta


def _parse_labeled_fields(body: str) -> dict[str, str]:
    cleaned = re.sub(r"<!--.*?-->", "", body or "", flags=re.DOTALL)
    cleaned = re.sub(r"^#\s*.+\n+", "", cleaned.strip(), count=1).strip()
    out: dict[str, str] = {}
    for m in _FIELD_RE.finditer(cleaned):
        key = m.group(1)
        val = m.group(2).strip()
        if key == "相关问题":
            out["question"] = val
        elif key == "关键词":
            out["keywords"] = val
        else:
            # 参考回答 / 参考回答-中文 / 参考回答-英文
            out.setdefault("answer", val)
            if key.endswith("-中文") or key == "参考回答":
                out["answer"] = val
    if "answer" not in out and cleaned:
        # Legacy absorb notes without FAQ labels: whole body is the answer.
        out["answer"] = cleaned
    return out


def learned_markdown_to_entry(path_name: str, body: str) -> AgentKbEntry:
    meta = _parse_meta(body)
    labeled = _parse_labeled_fields(body)
    stamp = path_name.replace("learned_", "").replace(".md", "") or datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    question = (labeled.get("question") or meta.get("related_question") or "").strip()
    answer = (labeled.get("answer") or "").strip()
    keywords = (labeled.get("keywords") or "").strip()
    if not question:
        # Fallback: first non-empty line of answer / body
        for line in answer.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                question = line[:200]
                break
        if not question:
            question = path_name
    if not keywords:
        keywords = "learned;absorb;自动学习"
    else:
        # Keep human keywords; append absorb tag if missing
        low = keywords.lower()
        if "absorb" not in low and "learned" not in low and "自动学习" not in keywords:
            keywords = f"{keywords};absorb"

    source_parts = [f"knowledge/learned/{path_name}"]
    if meta.get("chat_id"):
        source_parts.append(f"chat_id={meta['chat_id']}")
    if meta.get("sender"):
        source_parts.append(f"sender={meta['sender']}")
    elif meta.get("sender_id"):
        source_parts.append(f"sender_id={meta['sender_id']}")

    updated_at = meta.get("learned_at") or datetime.now().isoformat(timespec="seconds")

    return AgentKbEntry(
        entry_id=f"LEARN-{stamp}",
        category="Learned / 自动学习",
        question=question,
        answer=answer[:3500],
        keywords=keywords,
        source="; ".join(source_parts),
        updated_at=updated_at,
    )


def sync_learned_file_to_lark(
    path_name: str,
    body: str,
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    app_token: str | None = None,
    table_id: str | None = None,
) -> str | None:
    app_id = (app_id or os.getenv("LARK_APP_ID", "")).strip()
    app_secret = (app_secret or os.getenv("LARK_APP_SECRET", "")).strip()
    app_token = (app_token or "").strip()
    table_id = (table_id or "").strip()
    if not app_id or not app_secret or not app_token or not table_id:
        logger.info("Agent KB Lark sync skipped: missing credentials/table config")
        return None
    entry = learned_markdown_to_entry(path_name, body)
    try:
        record_id, action = upsert_entry_to_lark(
            entry,
            app_id=app_id,
            app_secret=app_secret,
            app_token=app_token,
            table_id=table_id,
        )
        logger.info(
            "Synced learned entry %s -> Lark record %s (%s)",
            entry.entry_id,
            record_id,
            action,
        )
        return record_id
    except LarkBitableError:
        logger.exception("Failed to sync learned entry %s to Lark", entry.entry_id)
        return None


def backfill_learned_dir_to_lark(
    learned_dir: Path,
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    app_token: str | None = None,
    table_id: str | None = None,
) -> dict[str, int]:
    """Upsert all learned_*.md files. Returns counts: created/updated/skipped/failed."""
    app_id = (app_id or os.getenv("LARK_APP_ID", "")).strip()
    app_secret = (app_secret or os.getenv("LARK_APP_SECRET", "")).strip()
    app_token = (app_token or "").strip()
    table_id = (table_id or "").strip()
    counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "total_files": 0}
    if not app_id or not app_secret or not app_token or not table_id:
        logger.error("backfill skipped: missing credentials/table config")
        return counts
    if not learned_dir.exists():
        return counts

    token = get_tenant_access_token(app_id, app_secret)
    ensure_agent_kb_fields(token, app_token, table_id)
    existing_ids = _index_by_entry_id(list_records(token, app_token, table_id))

    files = sorted(learned_dir.glob("learned_*.md"))
    counts["total_files"] = len(files)
    for path in files:
        try:
            body = path.read_text(encoding="utf-8")
            entry = learned_markdown_to_entry(path.name, body)
            if not entry.answer.strip():
                counts["skipped"] += 1
                continue
            _, action = upsert_entry_to_lark(
                entry,
                app_id=app_id,
                app_secret=app_secret,
                app_token=app_token,
                table_id=table_id,
                existing_ids=existing_ids,
            )
            counts[action] += 1
            logger.info("Backfill %s %s", action, entry.entry_id)
        except Exception:  # noqa: BLE001
            counts["failed"] += 1
            logger.exception("Backfill failed for %s", path.name)
    return counts
