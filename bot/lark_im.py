"""Lark IM helpers: resolve users, create group chats, send messages."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from bot.lark_bitable import LARK_API_BASE, LarkBitableError, _parse

logger = logging.getLogger(__name__)


def resolve_open_ids_by_emails(token: str, emails: list[str]) -> list[str]:
    """Resolve emails to open_ids. Requires contact:user.id:readonly (or equivalent)."""
    cleaned = [e.strip() for e in emails if e and str(e).strip()]
    if not cleaned:
        return []
    resp = requests.post(
        f"{LARK_API_BASE}/contact/v3/users/batch_get_id",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params={"user_id_type": "open_id"},
        json={"emails": cleaned},
        timeout=30,
    )
    data = _parse(resp, "batch_get_id")
    user_list = (data.get("data") or {}).get("user_list") or []
    open_ids: list[str] = []
    for item in user_list:
        oid = item.get("user_id") or item.get("open_id")
        if oid:
            open_ids.append(str(oid))
        else:
            logger.warning("No open_id for email=%s item=%s", item.get("email"), item)
    return open_ids


def create_group_chat(
    token: str,
    *,
    name: str,
    user_open_ids: list[str],
    description: str = "",
) -> dict[str, Any]:
    """Create a private group chat and add members. Returns chat data (incl. chat_id)."""
    members = [uid for uid in user_open_ids if uid]
    if len(members) < 1:
        raise LarkBitableError("create_group_chat requires at least 1 member open_id")

    payload: dict[str, Any] = {
        "name": name[:50],
        "description": (description or "")[:100],
        "user_id_list": members,
        "owner_id": members[0],
        "chat_mode": "group",
        "chat_type": "private",
        "join_message_visibility": "all_members",
        "membership_approval": "no_approval_required",
    }
    resp = requests.post(
        f"{LARK_API_BASE}/im/v1/chats",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params={"user_id_type": "open_id"},
        json=payload,
        timeout=30,
    )
    data = _parse(resp, "create chat")
    chat = (data.get("data") or {})
    if not chat.get("chat_id"):
        raise LarkBitableError(f"create chat: missing chat_id in {data}")
    return chat


def send_text_to_chat(token: str, chat_id: str, text: str) -> None:
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
    _parse(resp, "send message")
