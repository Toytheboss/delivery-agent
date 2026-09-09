"""TG tech-support escalation: quote + "tech support" → Lark → reply back to TG."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from telethon import TelegramClient
from telethon.tl.custom.message import Message

from bot.lark_bitable import LARK_API_BASE, get_tenant_access_token

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=8))

_BRAND_RE = re.compile(r"(?i)^\s*(?:bot\s*chain|botchain|botchian)\s*$")


def _strip_wrap(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"\'“”":
        s = s[1:-1].strip()
    return s.strip('"').strip("'").strip()


def project_name_from_chat_title(title: str) -> str:
    """Best-effort project name from TG title like 'Easy Work <> Bot Chain'."""
    t = _strip_wrap(title or "")
    t = re.sub(r"(?i)\s*Deployment\s*$", "", t).strip()
    t = _strip_wrap(t)
    if not t:
        return "未知项目"
    for sep in (" <> ", "<>", " × ", " x ", " X ", "｜", " | ", " — ", " - "):
        if sep not in t:
            continue
        left, right = (_strip_wrap(p) for p in t.split(sep, 1))
        left_brand = bool(_BRAND_RE.match(left))
        right_brand = bool(_BRAND_RE.match(right))
        if right_brand and left and not left_brand:
            return left
        if left_brand and right and not right_brand:
            return right
        if left:
            return left
    return t


_TECH_CMD_RE = re.compile(
    r"(?is)^\s*(?:[/@])?(?:tech[\s_-]*support|techsupport|/tech)\s*[!.。！]*\s*$"
)
_TICKET_IN_TEXT_RE = re.compile(r"\b(T-\d{8}-\d{4,})\b")


_LARK_AT_PLACEHOLDER_RE = re.compile(r"@_user_\d+")
_LARK_AT_TAG_RE = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE | re.DOTALL)


def sanitize_answer_for_tg(text: str) -> str:
    """Strip Lark @ placeholders/tags so TG clients do not see @_user_1."""
    s = (text or "").strip()
    s = _LARK_AT_TAG_RE.sub("", s)
    s = _LARK_AT_PLACEHOLDER_RE.sub("", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()



def is_tech_support_command(text: str) -> bool:
    return bool(_TECH_CMD_RE.match((text or "").strip()))


def _owner_name(config: Any) -> str:
    return str(getattr(config, "tech_support_owner", "") or "unknown").strip() or "unknown"


def _state_path(config: Any) -> Path:
    rel = (
        getattr(config, "tech_support_state_file", "")
        or "/opt/botchain-shared/tech_support_tickets.json"
    )
    path = Path(rel)
    return path if path.is_absolute() else ROOT / path


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"tickets": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"tickets": {}}
    if not isinstance(data, dict):
        return {"tickets": {}}
    tickets = data.get("tickets")
    if not isinstance(tickets, dict):
        data["tickets"] = {}
    return data


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _new_ticket_id() -> str:
    day = datetime.now(TZ).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:4].upper()
    return f"T-{day}-{suffix}"


def _lark_creds(config: Any) -> tuple[str, str]:
    app_id = (
        str(getattr(config, "tech_support_lark_app_id", "") or "").strip()
        or os.getenv("TECH_SUPPORT_LARK_APP_ID", "").strip()
        or os.getenv("LARK_APP_ID", "").strip()
    )
    app_secret = (
        str(getattr(config, "tech_support_lark_app_secret", "") or "").strip()
        or os.getenv("TECH_SUPPORT_LARK_APP_SECRET", "").strip()
        or os.getenv("LARK_APP_SECRET", "").strip()
    )
    return app_id, app_secret


def _send_lark_text(token: str, chat_id: str, text: str) -> str:
    """Send text (may include <at> tags). Returns message_id."""
    content = json.dumps({"text": text}, ensure_ascii=False)
    resp = requests.post(
        f"{LARK_API_BASE}/im/v1/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": content,
        },
        timeout=30,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise RuntimeError(f"lark send failed: {resp.status_code} {data}")
    msg_id = ((data.get("data") or {}).get("message_id")) or ""
    if not msg_id:
        raise RuntimeError(f"lark send missing message_id: {data}")
    return str(msg_id)


def _extract_text_from_lark_content(msg_type: str, content_raw: str) -> str:
    try:
        content = json.loads(content_raw or "{}")
    except Exception:  # noqa: BLE001
        return (content_raw or "").strip()
    if msg_type == "text":
        return str(content.get("text") or "").strip()
    if msg_type == "post":
        # Flatten post title + paragraphs
        parts: list[str] = []
        for lang_body in content.values():
            if not isinstance(lang_body, dict):
                continue
            title = lang_body.get("title")
            if title:
                parts.append(str(title))
            for block in lang_body.get("content") or []:
                if not isinstance(block, list):
                    continue
                line = []
                for span in block:
                    if isinstance(span, dict) and span.get("tag") == "text":
                        line.append(str(span.get("text") or ""))
                if line:
                    parts.append("".join(line))
        return "\n".join(parts).strip()
    return str(content.get("text") or content_raw or "").strip()


def _assignees_from_config(config: Any) -> list[dict[str, str]]:
    """Return [{open_id, name}, ...] for Lark @ mentions."""
    raw = getattr(config, "tech_support_assignees", None) or []
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            oid = str(item.get("open_id") or "").strip()
            name = str(item.get("name") or "").strip() or "tech"
            if oid:
                out.append({"open_id": oid, "name": name})
    # Backward compat: single cisco_* fields
    if not out:
        oid = str(getattr(config, "tech_support_cisco_open_id", "") or "").strip()
        name = str(getattr(config, "tech_support_cisco_name", "") or "Cisco-BE").strip()
        if oid:
            out.append({"open_id": oid, "name": name})
    return out


def build_lark_ticket_text(
    *,
    ticket_id: str,
    project_name: str,
    chat_title: str,
    question: str,
    asker: str,
    assignees: list[dict[str, str]] | None = None,
) -> str:
    q = (question or "").strip()
    if len(q) > 1200:
        q = q[:1200].rstrip() + "…"
    people = assignees or []
    if people:
        at = " ".join(
            f'<at user_id="{a["open_id"]}">{a.get("name") or "tech"}</at>' for a in people
        )
    else:
        at = "@tech"
    names = ", ".join(a.get("name") or "tech" for a in people) if people else "tech"
    return (
        f"{at}\n"
        f"【Tech Support】{ticket_id}\n"
        f"项目：{project_name or '未知项目'}\n"
        f"TG 群：{chat_title or '未知群'}\n"
        f"提问人：{asker or '未知'}\n"
        f"答疑：{names}\n"
        f"原文：\n{q or '(空)'}\n"
        f"——\n"
        f"请直接「回复本条消息」作答；Bot 会 quote 原 TG 问题回传到项目群。"
    )


async def escalate_tech_support(
    client: TelegramClient,
    config: Any,
    *,
    command_message: Message,
    chat_id: int,
    chat_title: str,
) -> str:
    """Create ticket, push Lark, ack in TG. Returns status text for reply."""
    if not bool(getattr(config, "tech_support_enabled", False)):
        return "Tech support is disabled."

    reply_id = getattr(command_message, "reply_to_msg_id", None)
    if not reply_id:
        return (
            "Please reply/quote the technical question first, then send `tech support`."
        )

    try:
        quoted = await command_message.get_reply_message()
    except Exception:  # noqa: BLE001
        quoted = None
    if not quoted:
        return "Could not load the quoted message. Please try again."

    question = (quoted.raw_text or "").strip()
    if not question and getattr(quoted, "message", None):
        question = str(quoted.message).strip()
    if not question:
        question = "[non-text message — see TG quote]"

    asker_name = ""
    try:
        sender = await quoted.get_sender()
        asker_name = (
            (getattr(sender, "username", None) and f"@{sender.username}")
            or (getattr(sender, "first_name", None) or "")
            or str(getattr(sender, "id", "") or "")
        )
    except Exception:  # noqa: BLE001
        asker_name = ""

    project_name = project_name_from_chat_title(chat_title)
    ticket_id = _new_ticket_id()
    owner = _owner_name(config)
    lark_chat_id = str(getattr(config, "tech_support_lark_chat_id", "") or "").strip()
    assignees = _assignees_from_config(config)
    assignee_names = ", ".join(a.get("name") or "tech" for a in assignees) or "tech"

    if not lark_chat_id:
        return "Tech support Lark chat is not configured."

    app_id, app_secret = _lark_creds(config)
    if not app_id or not app_secret:
        return "Tech support Lark credentials missing."

    body = build_lark_ticket_text(
        ticket_id=ticket_id,
        project_name=project_name,
        chat_title=chat_title,
        question=question,
        asker=asker_name,
        assignees=assignees,
    )

    try:
        token = get_tenant_access_token(app_id, app_secret)
        lark_msg_id = _send_lark_text(token, lark_chat_id, body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tech support: Lark send failed")
        return f"Failed to push to Lark: {exc}"

    path = _state_path(config)
    state = _load_state(path)
    tickets: dict[str, Any] = state.setdefault("tickets", {})
    tickets[ticket_id] = {
        "ticket_id": ticket_id,
        "status": "open",
        "owner": owner,
        "tg_chat_id": int(chat_id),
        "tg_question_message_id": int(quoted.id),
        "tg_command_message_id": int(command_message.id),
        "chat_title": chat_title,
        "project_name": project_name,
        "question_text": question[:2000],
        "asker": asker_name,
        "lark_chat_id": lark_chat_id,
        "lark_message_id": lark_msg_id,
        "created_at": time.time(),
        "answered_at": None,
        "answer_text": "",
        "lark_answer_message_id": "",
    }
    # Index by Lark root message for fast reply match
    idx = state.setdefault("by_lark_message_id", {})
    idx[lark_msg_id] = ticket_id
    _save_state(path, state)

    logger.info(
        "tech support opened %s chat=%s q_msg=%s lark_msg=%s owner=%s",
        ticket_id,
        chat_id,
        quoted.id,
        lark_msg_id,
        owner,
    )
    return (
        f"Escalated to Lark tech support as {ticket_id}. "
        f"@{assignee_names} will be notified; answer will be quoted back here."
    )


def _find_ticket_for_lark_reply(
    state: dict[str, Any],
    *,
    parent_id: str | None,
    root_id: str | None,
    text: str,
) -> dict[str, Any] | None:
    tickets: dict[str, Any] = state.get("tickets") or {}
    idx: dict[str, Any] = state.get("by_lark_message_id") or {}
    for key in (parent_id, root_id):
        if not key:
            continue
        tid = idx.get(key)
        if tid and tid in tickets:
            return tickets[tid]
        # Fallback: parent_id equals stored lark_message_id
        for t in tickets.values():
            if isinstance(t, dict) and t.get("lark_message_id") == key:
                return t
    m = _TICKET_IN_TEXT_RE.search(text or "")
    if m:
        tid = m.group(1)
        if tid in tickets:
            return tickets[tid]
    return None



def maybe_auto_learn_tech_support(
    config: Any,
    ticket: dict[str, Any],
    answer: str,
    *,
    kb: Any | None = None,
) -> dict[str, Any]:
    """Persist Q&A into knowledge + Agent KB after a successful TG delivery."""
    out: dict[str, Any] = {"learned": False, "reason": "", "path": "", "lark_record_id": ""}
    if not bool(getattr(config, "tech_support_auto_learn", True)):
        out["reason"] = "disabled"
        return out

    question = sanitize_answer_for_tg(str(ticket.get("question_text") or "")).strip()
    answer = sanitize_answer_for_tg(answer or "").strip()
    min_chars = int(getattr(config, "tech_support_auto_learn_min_chars", 20) or 20)
    if len(question) < 5:
        out["reason"] = "question_too_short"
        return out
    if len(answer) < min_chars:
        out["reason"] = "answer_too_short"
        return out

    # Dedup by ticket_id across shared learn state
    learn_state_path = Path(
        getattr(config, "tech_support_auto_learn_state_file", "")
        or "/opt/botchain-shared/tech_support_auto_learn.json"
    )
    if not learn_state_path.is_absolute():
        learn_state_path = ROOT / learn_state_path
    try:
        learn_state = json.loads(learn_state_path.read_text(encoding="utf-8")) if learn_state_path.exists() else {}
    except Exception:  # noqa: BLE001
        learn_state = {}
    if not isinstance(learn_state, dict):
        learn_state = {}
    learned_ids = learn_state.setdefault("ticket_ids", [])
    if not isinstance(learned_ids, list):
        learned_ids = []
        learn_state["ticket_ids"] = learned_ids
    tid = str(ticket.get("ticket_id") or "")
    if tid and tid in learned_ids:
        out["reason"] = "already_learned"
        return out

    try:
        from bot.learn import save_learned_content
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"import_learn_failed:{exc}"
        return out

    subdir = str(getattr(config, "learn_subdirectory", "") or "learned")
    knowledge_dirs: list[Path] = []
    primary = Path(getattr(config, "knowledge_dir"))
    knowledge_dirs.append(primary)
    # Keep Roy FAQ in sync when Josh delivers the answer
    qa_knowledge = Path("/opt/botchain-qa-tg-bot/knowledge")
    if qa_knowledge.is_dir() and qa_knowledge.resolve() != primary.resolve():
        knowledge_dirs.append(qa_knowledge)

    meta_extra = (
        f"<!-- source: tech_support -->\n"
        f"<!-- ticket_id: {tid} -->\n"
        f"<!-- project: {(ticket.get('project_name') or '').replace('--', '- -')} -->\n"
    )

    saved: list[str] = []
    primary_path: Path | None = None
    for kd in knowledge_dirs:
        try:
            path = save_learned_content(
                answer,
                kd,
                chat_id=int(ticket.get("tg_chat_id") or 0),
                sender_id=None,
                sender_username="tech_support",
                subdirectory=subdir,
                related_question=question,
            )
            # Append tech_support meta markers for Agent KB / audit
            try:
                body = path.read_text(encoding="utf-8")
                if "source: tech_support" not in body:
                    body = body.replace(
                        f"<!-- sender: @tech_support -->\n",
                        f"<!-- sender: @tech_support -->\n{meta_extra}",
                        1,
                    )
                    path.write_text(body, encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            saved.append(str(path))
            if primary_path is None:
                primary_path = path
        except Exception:  # noqa: BLE001
            logger.exception("tech support auto-learn save failed dir=%s", kd)

    if not primary_path:
        out["reason"] = "save_failed"
        return out

    record_id = ""
    if bool(getattr(config, "agent_kb_lark_sync_enabled", False)):
        try:
            from bot.agent_kb_sync import sync_learned_file_to_lark

            record_id = sync_learned_file_to_lark(
                primary_path.name,
                primary_path.read_text(encoding="utf-8"),
                app_token=str(getattr(config, "agent_kb_app_token", "") or ""),
                table_id=str(getattr(config, "agent_kb_table_id", "") or ""),
            ) or ""
        except Exception:  # noqa: BLE001
            logger.exception("tech support Agent KB sync failed ticket=%s", tid)

    if kb is not None:
        try:
            kb.reload()
        except Exception:  # noqa: BLE001
            logger.exception("tech support kb.reload failed")

    if tid:
        learned_ids.append(tid)
        learn_state["ticket_ids"] = learned_ids[-500:]
        try:
            learn_state_path.parent.mkdir(parents=True, exist_ok=True)
            learn_state_path.write_text(
                json.dumps(learn_state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            logger.exception("tech support auto-learn state save failed")

    try:
        from bot.workflow_events import append_event

        append_event(
            "tech_support_auto_learn",
            "tech_support",
            project_name=str(ticket.get("project_name") or ""),
            text=f"{tid} Q&A 已自动学习并同步 Agent 词条库",
            chat_id=ticket.get("tg_chat_id"),
            knowledge_file=primary_path.name,
            lark_record_id=record_id,
            ticket_id=tid,
        )
    except Exception:  # noqa: BLE001
        pass

    out.update(
        {
            "learned": True,
            "reason": "ok",
            "path": str(primary_path),
            "lark_record_id": record_id,
            "saved_paths": saved,
        }
    )
    logger.info(
        "tech support auto-learn ticket=%s file=%s lark=%s",
        tid,
        primary_path.name,
        record_id or "none",
    )
    return out



async def deliver_answer_to_tg(
    client: TelegramClient,
    config: Any,
    ticket: dict[str, Any],
    answer: str,
    *,
    lark_answer_message_id: str = "",
    kb: Any | None = None,
) -> dict[str, Any]:
    """Quote original TG question with the Lark answer. Only for this bot's tickets."""
    result = {"sent": False, "reason": ""}
    owner = _owner_name(config)
    # Strict: only the escalating bot posts back to TG
    if ticket.get("owner") and ticket.get("owner") != owner:
        result["reason"] = "owner_mismatch"
        return result
    if ticket.get("status") == "sent":
        result["reason"] = "already_sent"
        return result

    answer = sanitize_answer_for_tg(answer or "")
    # Strip leading ticket id if tech pasted it
    answer = re.sub(r"(?is)^\s*" + re.escape(str(ticket.get("ticket_id") or "")) + r"\s*[:：\-]?\s*", "", answer).strip()
    answer = sanitize_answer_for_tg(answer)
    if not answer:
        result["reason"] = "empty_answer"
        return result

    tg_chat_id = int(ticket["tg_chat_id"])
    q_msg_id = int(ticket["tg_question_message_id"])
    header = f"[Tech Support {ticket.get('ticket_id')}]"
    body = f"{header}\n{answer}"
    try:
        await client.send_message(tg_chat_id, body, reply_to=q_msg_id, link_preview=False)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tech support: TG reply failed ticket=%s", ticket.get("ticket_id"))
        result["reason"] = f"tg_send_failed:{exc}"
        return result

    ticket["status"] = "sent"
    ticket["answered_at"] = time.time()
    ticket["answer_text"] = answer[:4000]
    ticket["lark_answer_message_id"] = lark_answer_message_id or ticket.get("lark_answer_message_id") or ""

    path = _state_path(config)
    state = _load_state(path)
    tid = str(ticket.get("ticket_id"))
    state.setdefault("tickets", {})[tid] = ticket
    if ticket.get("lark_message_id"):
        state.setdefault("by_lark_message_id", {})[ticket["lark_message_id"]] = tid
    _save_state(path, state)

    result["sent"] = True
    result["reason"] = "sent"
    logger.info("tech support answered %s → tg %s/%s", tid, tg_chat_id, q_msg_id)
    try:
        learn_meta = maybe_auto_learn_tech_support(config, ticket, answer, kb=kb)
        result["auto_learn"] = learn_meta
    except Exception:  # noqa: BLE001
        logger.exception("tech support auto-learn failed ticket=%s", tid)
        result["auto_learn"] = {"learned": False, "reason": "exception"}
    return result


def ingest_lark_message_event(config: Any, event_data: dict[str, Any]) -> dict[str, Any] | None:
    """Parse Lark im.message.receive_v1 payload → ticket+answer candidate or None."""
    message = (event_data.get("message") or {}) if isinstance(event_data, dict) else {}
    if not message:
        return None
    chat_id = str(message.get("chat_id") or "")
    expected = str(getattr(config, "tech_support_lark_chat_id", "") or "").strip()
    if expected and chat_id and chat_id != expected:
        return None

    # Ignore bot's own messages
    sender = event_data.get("sender") or {}
    if str(sender.get("sender_type") or "").lower() == "app":
        return None

    parent_id = str(message.get("parent_id") or "") or None
    root_id = str(message.get("root_id") or "") or None
    msg_type = str(message.get("message_type") or message.get("msg_type") or "text")
    content_raw = str(message.get("content") or "")
    text = _extract_text_from_lark_content(msg_type, content_raw)
    if not text:
        return None

    # Must be a reply to ticket (or contain ticket id)
    if not parent_id and not root_id and not _TICKET_IN_TEXT_RE.search(text):
        return None

    path = _state_path(config)
    state = _load_state(path)
    ticket = _find_ticket_for_lark_reply(
        state, parent_id=parent_id, root_id=root_id, text=text
    )
    if not ticket:
        return None
    if ticket.get("status") == "sent":
        return None

    return {
        "ticket": ticket,
        "answer": text,
        "lark_answer_message_id": str(message.get("message_id") or ""),
    }


async def process_lark_reply_candidate(
    client: TelegramClient,
    config: Any,
    candidate: dict[str, Any],
    *,
    kb: Any | None = None,
) -> dict[str, Any]:
    ticket = candidate["ticket"]
    owner = _owner_name(config)
    if ticket.get("owner") and ticket.get("owner") != owner:
        return {"sent": False, "reason": "owner_mismatch"}
    return await deliver_answer_to_tg(
        client,
        config,
        ticket,
        candidate.get("answer") or "",
        lark_answer_message_id=candidate.get("lark_answer_message_id") or "",
        kb=kb,
    )


def _list_recent_lark_messages(token: str, chat_id: str, page_size: int = 20) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{LARK_API_BASE}/im/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "container_id_type": "chat",
            "container_id": chat_id,
            "sort_type": "ByCreateTimeDesc",
            "page_size": page_size,
        },
        timeout=30,
    )
    data = resp.json() if resp.content else {}
    if data.get("code") not in (0, None):
        logger.warning("tech support poll list messages failed: %s", data)
        return []
    return list((data.get("data") or {}).get("items") or [])


async def poll_open_ticket_replies(client: TelegramClient, config: Any, *, kb: Any | None = None) -> int:
    """Poll Lark chat for replies to open tickets owned by this bot. Returns sent count."""
    if not bool(getattr(config, "tech_support_enabled", False)):
        return 0
    if not bool(getattr(config, "tech_support_poll_enabled", True)):
        return 0

    lark_chat_id = str(getattr(config, "tech_support_lark_chat_id", "") or "").strip()
    if not lark_chat_id:
        return 0
    app_id, app_secret = _lark_creds(config)
    if not app_id or not app_secret:
        return 0

    path = _state_path(config)
    state = _load_state(path)
    owner = _owner_name(config)
    open_tickets = [
        t
        for t in (state.get("tickets") or {}).values()
        if isinstance(t, dict)
        and t.get("status") == "open"
        and t.get("owner") == owner
    ]
    if not open_tickets:
        return 0

    try:
        token = get_tenant_access_token(app_id, app_secret)
        items = _list_recent_lark_messages(token, lark_chat_id, page_size=50)
    except Exception:  # noqa: BLE001
        logger.exception("tech support poll failed")
        return 0

    open_by_lark = {str(t.get("lark_message_id")): t for t in open_tickets if t.get("lark_message_id")}
    sent = 0
    seen_answer_ids = {
        str(t.get("lark_answer_message_id") or "")
        for t in (state.get("tickets") or {}).values()
        if isinstance(t, dict)
    }

    for item in items:
        msg_id = str(item.get("message_id") or "")
        if not msg_id or msg_id in seen_answer_ids:
            continue
        # skip app messages
        sender = item.get("sender") or {}
        if str(sender.get("sender_type") or "").lower() == "app":
            continue
        parent_id = str(item.get("parent_id") or "") or None
        root_id = str(item.get("root_id") or "") or None
        msg_type = str(item.get("msg_type") or "text")
        body = item.get("body") or {}
        content_raw = str(body.get("content") or "")
        text = _extract_text_from_lark_content(msg_type, content_raw)
        if not text:
            continue

        ticket = None
        for key in (parent_id, root_id):
            if key and key in open_by_lark:
                ticket = open_by_lark[key]
                break
        if not ticket:
            m = _TICKET_IN_TEXT_RE.search(text)
            if m:
                tid = m.group(1)
                for t in open_tickets:
                    if t.get("ticket_id") == tid:
                        ticket = t
                        break
        if not ticket:
            continue

        result = await deliver_answer_to_tg(
            client,
            config,
            ticket,
            text,
            lark_answer_message_id=msg_id,
            kb=kb,
        )
        if result.get("sent"):
            sent += 1
            seen_answer_ids.add(msg_id)
            # refresh open maps after send
            open_tickets = [t for t in open_tickets if t.get("ticket_id") != ticket.get("ticket_id")]
            open_by_lark = {
                str(t.get("lark_message_id")): t
                for t in open_tickets
                if t.get("lark_message_id")
            }
    return sent


async def tech_support_poll_loop(client: TelegramClient, config: Any, *, kb: Any | None = None) -> None:
    import asyncio

    interval = int(getattr(config, "tech_support_poll_seconds", 45) or 45)
    interval = max(15, interval)
    logger.info("tech support poll loop every %ss", interval)
    while True:
        try:
            n = await poll_open_ticket_replies(client, config, kb=kb)
            if n:
                logger.info("tech support poll delivered %s answer(s)", n)
        except Exception:  # noqa: BLE001
            logger.exception("tech support poll loop error")
        await asyncio.sleep(interval)
