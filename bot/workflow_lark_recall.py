"""Roy tells roy's lark agent to recall a message it sent.

Private chat (preferred, nothing extra in the group):

    <original text>
    recall

or one line ``recall 原文`` / ``recall + 原文``.
One unique match is recalled. Several matches are listed, none recalled.

Group chat: reply to the bot message with only ``recall``. The bot recalls that
message, then tries to recall the command so the group stays clean (needs admin).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bot.workflow_lark_relay import (
    _event_parts,
    _reply,
    _sender_open_id,
    claim_message,
    list_groups,
    owner_open_ids,
)

logger = logging.getLogger(__name__)

_RECALL_LINE_RE = re.compile(r"(?is)^recall\s*$")
_RECALL_INLINE_RE = re.compile(r"(?is)^recall(?:\s*\+\s*|\s+)(.+)$")
_MIN_SNIPPET = 8


def parse_recall_command(text: str) -> tuple[str, bool] | None:
    """Return (snippet, True) for a recall command.

    Empty snippet means reply-to-message recall. None means not a command.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    lines = (text or "").splitlines()
    idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            idx = i
            break
    if idx is None:
        return None
    last = lines[idx].strip()
    if _RECALL_LINE_RE.match(last):
        body = "\n".join(lines[:idx]).strip()
        return body, True
    inline = _RECALL_INLINE_RE.match(last) or _RECALL_INLINE_RE.match(raw)
    if inline:
        snippet = inline.group(1).strip()
        if snippet:
            return snippet, True
    return None


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def pick_recall_hits(
    items: list[dict[str, str]], snippet: str
) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    needle = _fold(snippet)
    if not needle:
        return None, []
    hits = [item for item in items if needle in _fold(item.get("text") or "")]
    if len(hits) == 1:
        return hits[0], hits
    return None, hits


def _api(token: str, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    import requests

    from bot.lark_bitable import LARK_API_BASE

    extra_headers = kwargs.pop("headers", None) or {}
    timeout = kwargs.pop("timeout", 20)
    resp = requests.request(
        method,
        f"{LARK_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}", **extra_headers},
        timeout=timeout,
        **kwargs,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise RuntimeError(
            f"{method} {path} failed: {resp.status_code} {data.get('code')} {data.get('msg')}"
        )
    return data if isinstance(data, dict) else {}


def _message_text(item: dict[str, Any]) -> str:
    from bot.workflow_tech_support import _extract_text_from_lark_content

    msg_type = str(item.get("msg_type") or item.get("message_type") or "text")
    content = item.get("content") or ""
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)
    return _extract_text_from_lark_content(msg_type, str(content))


def _sender_is_app(item: dict[str, Any]) -> bool:
    sender = item.get("sender") or {}
    if not isinstance(sender, dict):
        return False
    kind = str(sender.get("sender_type") or sender.get("id_type") or "").lower()
    return kind in {"app", "bot"}


def recall_message(token: str, message_id: str) -> None:
    _api(token, "DELETE", f"/im/v1/messages/{message_id}")


def get_message(token: str, message_id: str) -> dict[str, Any] | None:
    data = _api(token, "GET", f"/im/v1/messages/{message_id}")
    items = (data.get("data") or {}).get("items") or []
    if items and isinstance(items[0], dict):
        return items[0]
    return None


def _collect_message_ids(blob: dict[str, Any]) -> list[str]:
    items = blob.get("items") or blob.get("messages") or []
    ids: list[str] = []
    for item in items:
        if isinstance(item, str) and item.startswith("om_"):
            ids.append(item)
            continue
        if not isinstance(item, dict):
            continue
        mid = str(item.get("message_id") or "").strip()
        if mid:
            ids.append(mid)
    return ids


def _search_message_ids(token: str, query: str, chat_id: str = "") -> list[str]:
    payload: dict[str, Any] = {"query": query, "page_size": 20}
    filt: dict[str, Any] = {"sender_type": "bot"}
    if chat_id:
        filt["chat_ids"] = [chat_id]
    payload["filter"] = filt
    try:
        data = _api(token, "POST", "/im/v1/messages/search", json=payload)
        return _collect_message_ids(data.get("data") or {})
    except Exception:
        logger.exception("im messages/search failed, trying search/v2")
    payload2: dict[str, Any] = {"query": query, "page_size": 20, "from_type": "bot"}
    if chat_id:
        payload2["chat_ids"] = [chat_id]
    data = _api(token, "POST", "/search/v2/message", json=payload2)
    return _collect_message_ids(data.get("data") or {})


def _mget_messages(token: str, message_ids: list[str]) -> list[dict[str, Any]]:
    if not message_ids:
        return []
    params = [("message_ids", mid) for mid in message_ids[:50]]
    data = _api(token, "GET", "/im/v1/messages/mget", params=params)
    return list((data.get("data") or {}).get("items") or [])


def _scan_chat_messages(token: str, chat_id: str) -> list[dict[str, Any]]:
    data = _api(
        token,
        "GET",
        "/im/v1/messages",
        params={
            "container_id_type": "chat",
            "container_id": chat_id,
            "sort_type": "ByCreateTimeDesc",
            "page_size": 50,
        },
    )
    return list((data.get("data") or {}).get("items") or [])


def _as_hit(item: dict[str, Any], chat_name: str = "") -> dict[str, str] | None:
    if item.get("deleted") is True:
        return None
    if not _sender_is_app(item):
        return None
    mid = str(item.get("message_id") or "").strip()
    text = _message_text(item)
    if not mid or not text:
        return None
    return {
        "id": mid,
        "text": text,
        "chat_id": str(item.get("chat_id") or ""),
        "chat_name": chat_name or str(item.get("chat_id") or ""),
    }


def find_bot_messages(
    token: str, snippet: str, *, chat_id: str = ""
) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any], chat_name: str = "") -> None:
        hit = _as_hit(item, chat_name)
        if not hit or hit["id"] in seen:
            return
        if _fold(snippet) not in _fold(hit["text"]):
            return
        seen.add(hit["id"])
        hits.append(hit)

    try:
        ids = _search_message_ids(token, snippet, chat_id=chat_id)
        items: list[dict[str, Any]] = []
        try:
            items = _mget_messages(token, ids)
        except Exception:
            logger.exception("lark recall mget failed, fetching one by one")
            for mid in ids:
                try:
                    one = get_message(token, mid)
                except Exception:
                    one = None
                if one:
                    items.append(one)
        for item in items:
            add(item)
    except Exception:
        logger.exception("lark recall search API failed, scanning chats")

    if hits:
        return hits

    chats = [{"id": chat_id, "name": ""}] if chat_id else list_groups(token)
    for chat in chats[:40]:
        cid = str(chat.get("id") or "").strip()
        if not cid:
            continue
        try:
            for item in _scan_chat_messages(token, cid):
                add(item, str(chat.get("name") or ""))
        except Exception:
            logger.exception("lark recall scan failed chat=%s", cid)
    return hits


def _format_hits(hits: list[dict[str, str]]) -> str:
    lines = []
    for item in hits[:8]:
        preview = re.sub(r"\s+", " ", item.get("text") or "")[:80]
        where = item.get("chat_name") or "群"
        lines.append(f"- {where}：{preview}")
    extra = len(hits) - len(lines)
    if extra > 0:
        lines.append(f"- 还有 {extra} 条")
    return "\n".join(lines)


def maybe_handle_lark_recall(
    config: Any, event_data: dict[str, Any]
) -> dict[str, Any] | None:
    """Handle a recall command. None means this event is not a command."""
    if not getattr(config, "lark_relay_enabled", True):
        return None
    if not isinstance(event_data, dict):
        return None
    message, sender = _event_parts(event_data)
    if not message:
        return None
    if str(sender.get("sender_type") or "").lower() == "app":
        return None

    from bot.lark_bitable import get_tenant_access_token
    from bot.workflow_tech_support import _extract_text_from_lark_content, _lark_creds

    msg_type = str(message.get("message_type") or message.get("msg_type") or "text")
    text = _extract_text_from_lark_content(msg_type, str(message.get("content") or ""))
    parsed = parse_recall_command(text)
    if parsed is None:
        return None
    snippet, _ok = parsed
    chat_type = str(message.get("chat_type") or "")
    parent_id = str(message.get("parent_id") or "").strip()
    chat_id = str(message.get("chat_id") or "")
    command_id = str(message.get("message_id") or "")
    is_p2p = chat_type == "p2p"

    if not is_p2p and not snippet and not parent_id:
        return None
    if not is_p2p and snippet and not parent_id and len(_fold(snippet)) < _MIN_SNIPPET:
        return None

    if command_id and not claim_message(command_id):
        return {"ok": True, "recall": "duplicate"}

    app_id, app_secret = _lark_creds(config)
    if not app_id or not app_secret:
        logger.error("lark recall missing app credentials")
        return {"ok": False, "recall": "no_credentials"}
    try:
        token = get_tenant_access_token(app_id, app_secret)
    except Exception:
        logger.exception("lark recall token failed")
        return {"ok": False, "recall": "token_failed"}

    sender_id = _sender_open_id(sender)
    allowed = owner_open_ids(config)
    if not allowed or sender_id not in allowed:
        if is_p2p:
            _reply(token, chat_id, "这条指令只接受 Roy 的私聊。")
        logger.info("lark recall rejected sender=%s chat=%s", sender_id, chat_id)
        return {"ok": True, "recall": "forbidden"}

    target_id = ""
    if parent_id and not snippet:
        try:
            parent = get_message(token, parent_id)
        except Exception as exc:
            logger.exception("lark recall get parent failed")
            if is_p2p:
                _reply(token, chat_id, f"找不到要撤回的消息：{exc}")
            return {"ok": False, "recall": "parent_missing"}
        if parent is None or not _sender_is_app(parent):
            note = "只能撤回智能体自己发的消息。"
            if is_p2p:
                _reply(token, chat_id, note)
            elif command_id:
                try:
                    recall_message(token, command_id)
                except Exception:
                    logger.exception("lark recall could not hide the command")
            return {"ok": True, "recall": "not_bot"}
        target_id = parent_id
    else:
        if len(_fold(snippet)) < _MIN_SNIPPET:
            _reply(
                token,
                chat_id,
                "把要撤回的原文放在上面，最后一行写 recall。原文至少几个字，避免撤错。",
            )
            return {"ok": True, "recall": "need_snippet"}
        scope = "" if is_p2p else chat_id
        try:
            found = find_bot_messages(token, snippet, chat_id=scope)
        except Exception as exc:
            logger.exception("lark recall find failed")
            if is_p2p:
                _reply(token, chat_id, f"查找失败：{exc}")
            return {"ok": False, "recall": "search_failed"}
        picked, hits = pick_recall_hits(found, snippet)
        if picked is None:
            if not hits:
                _reply(token, chat_id, "没有找到智能体发过的这条消息。原文再贴全一点。")
                return {"ok": True, "recall": "not_found"}
            _reply(
                token,
                chat_id,
                "找到多条，没有撤回。把原文再贴全一点：\n" + _format_hits(hits),
            )
            return {"ok": True, "recall": "ambiguous", "count": len(hits)}
        target_id = picked["id"]

    try:
        recall_message(token, target_id)
    except Exception as exc:
        logger.exception("lark recall delete failed")
        if is_p2p:
            _reply(token, chat_id, f"撤回失败：{exc}")
        return {"ok": False, "recall": "delete_failed"}

    if not is_p2p and command_id:
        try:
            recall_message(token, command_id)
        except Exception:
            logger.exception("lark recall could not hide the command")

    if is_p2p:
        _reply(token, chat_id, "已撤回。")
    logger.info("lark recall ok message=%s", target_id)
    return {"ok": True, "recall": "ok", "message_id": target_id}
