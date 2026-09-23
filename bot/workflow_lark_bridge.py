"""Bridge replies through roy's lark agent after a send-to.

send to opens a 24h session. The other person DMs the bot (or replies to the
bot in a group) → push to Roy. Roy replies to that push → send back, quoting
their last message when possible.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from bot.workflow_lark_relay import (
    _event_parts,
    _reply,
    _sender_open_id,
    claim_message,
    log_sent_message,
    owner_open_ids,
)

logger = logging.getLogger(__name__)

_TTL_SECONDS = 24 * 3600
_KEEP_SECONDS = 7 * 24 * 3600
_MAX_OUTBOUND = 20
_MAX_BRIDGE = 50
_MAX_SESSIONS = 80


def _sessions_path() -> Path:
    override = os.getenv("LARK_RELAY_SESSIONS", "").strip()
    if override:
        return Path(override)
    shared = Path("/opt/botchain-shared/lark_relay_sessions.json")
    if shared.parent.is_dir():
        return shared
    return Path("data/lark_relay_sessions.json")


def format_inbound_push(name: str, text: str, group_name: str = "") -> str:
    who = (name or "对方").strip() or "对方"
    body = (text or "").strip() or "[非文字，先只转文字]"
    if group_name:
        return f"{who}（{group_name}）：{body}"
    return f"{who}：{body}"


def session_active(session: dict[str, Any], now: float | None = None) -> bool:
    now = time.time() if now is None else now
    try:
        updated = float(session.get("updated_ts") or 0)
    except (TypeError, ValueError):
        return False
    return (now - updated) <= _TTL_SECONDS


def _prune(sessions: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    kept = []
    for item in sessions:
        if not isinstance(item, dict):
            continue
        try:
            updated = float(item.get("updated_ts") or 0)
        except (TypeError, ValueError):
            continue
        if now - updated > _KEEP_SECONDS:
            continue
        kept.append(item)
    return kept[-_MAX_SESSIONS:]


def _load_sessions() -> list[dict[str, Any]]:
    path = _sessions_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, dict):
        raw = raw.get("sessions") or []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _save_sessions(sessions: list[dict[str, Any]]) -> None:
    path = _sessions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps({"sessions": sessions}, ensure_ascii=False))
            handle.flush()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _session_key(kind: str, peer_id: str) -> str:
    return f"{kind}:{peer_id}"


def upsert_session(
    *,
    kind: str,
    peer_id: str,
    peer_name: str,
    roy_chat_id: str,
    outbound_message_id: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now is None else now
    kind = "group" if kind == "group" else "user"
    peer_id = (peer_id or "").strip()
    if not peer_id:
        return {}
    key = _session_key(kind, peer_id)
    sessions = _prune(_load_sessions(), now)
    found: dict[str, Any] | None = None
    for item in sessions:
        if _session_key(str(item.get("kind") or ""), str(item.get("peer_id") or "")) == key:
            found = item
            break
    if found is None:
        found = {
            "kind": kind,
            "peer_id": peer_id,
            "peer_name": peer_name or "",
            "roy_chat_id": roy_chat_id or "",
            "outbound_ids": [],
            "bridge_ids": [],
            "last_peer_message_id": "",
            "updated_ts": now,
        }
        sessions.append(found)
    found["kind"] = kind
    found["peer_id"] = peer_id
    if peer_name:
        found["peer_name"] = peer_name
    if roy_chat_id:
        found["roy_chat_id"] = roy_chat_id
    found["updated_ts"] = now
    outbound = list(found.get("outbound_ids") or [])
    if outbound_message_id and outbound_message_id not in outbound:
        outbound.append(outbound_message_id)
    found["outbound_ids"] = outbound[-_MAX_OUTBOUND:]
    _save_sessions(sessions)
    return found


def _touch(
    session: dict[str, Any],
    *,
    outbound_message_id: str = "",
    bridge_message_id: str = "",
    last_peer_message_id: str = "",
    now: float | None = None,
) -> None:
    now = time.time() if now is None else now
    sessions = _prune(_load_sessions(), now)
    key = _session_key(str(session.get("kind") or ""), str(session.get("peer_id") or ""))
    for item in sessions:
        if _session_key(str(item.get("kind") or ""), str(item.get("peer_id") or "")) != key:
            continue
        item["updated_ts"] = now
        if last_peer_message_id:
            item["last_peer_message_id"] = last_peer_message_id
        if outbound_message_id:
            outbound = list(item.get("outbound_ids") or [])
            if outbound_message_id not in outbound:
                outbound.append(outbound_message_id)
            item["outbound_ids"] = outbound[-_MAX_OUTBOUND:]
        if bridge_message_id:
            bridged = list(item.get("bridge_ids") or [])
            if bridge_message_id not in bridged:
                bridged.append(bridge_message_id)
            item["bridge_ids"] = bridged[-_MAX_BRIDGE:]
        session.update(item)
        break
    _save_sessions(sessions)


def find_session_by_peer(
    kind: str, peer_id: str, *, now: float | None = None, require_active: bool = True
) -> dict[str, Any] | None:
    now = time.time() if now is None else now
    key = _session_key("group" if kind == "group" else "user", (peer_id or "").strip())
    for item in _load_sessions():
        if _session_key(str(item.get("kind") or ""), str(item.get("peer_id") or "")) != key:
            continue
        if require_active and not session_active(item, now):
            return None
        return item
    return None


def find_session_by_bridge(
    message_id: str, *, now: float | None = None
) -> dict[str, Any] | None:
    now = time.time() if now is None else now
    message_id = (message_id or "").strip()
    if not message_id:
        return None
    for item in _load_sessions():
        ids = [str(x) for x in (item.get("bridge_ids") or [])]
        if message_id in ids:
            return item
    return None


def match_inbound(
    message: dict[str, Any],
    sender: dict[str, Any],
    *,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Session for an inbound message from the other person. None if ignore."""
    now = time.time() if now is None else now
    sender_id = _sender_open_id(sender)
    chat_type = str(message.get("chat_type") or "")
    chat_id = str(message.get("chat_id") or "").strip()
    parent_id = str(message.get("parent_id") or "").strip()
    root_id = str(message.get("root_id") or "").strip()
    if chat_type == "p2p":
        if not sender_id:
            return None
        return find_session_by_peer("user", sender_id, now=now, require_active=True)
    if not chat_id:
        return None
    session = find_session_by_peer("group", chat_id, now=now, require_active=True)
    if not session:
        return None
    outbound = {str(item) for item in (session.get("outbound_ids") or []) if str(item)}
    if parent_id in outbound or root_id in outbound:
        return session
    return None


def _reply_to_message(token: str, message_id: str, text: str) -> str:
    import requests

    from bot.lark_bitable import LARK_API_BASE

    content = json.dumps({"text": text}, ensure_ascii=False)
    resp = requests.post(
        f"{LARK_API_BASE}/im/v1/messages/{message_id}/reply",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"content": content, "msg_type": "text"},
        timeout=30,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise RuntimeError(
            f"reply failed: {resp.status_code} {data.get('code')} {data.get('msg')}"
        )
    return str(((data.get("data") or {}).get("message_id")) or "")


def _send_plain(token: str, kind: str, target_id: str, text: str) -> str:
    from bot.workflow_lark_relay import _send_to

    target_kind = "group" if kind == "group" else "user"
    return _send_to(token, {"kind": target_kind, "id": target_id, "name": ""}, text)


def _user_name(token: str, open_id: str, fallback: str) -> str:
    import requests

    from bot.lark_bitable import LARK_API_BASE

    if not open_id:
        return fallback
    try:
        resp = requests.get(
            f"{LARK_API_BASE}/contact/v3/users/{open_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"user_id_type": "open_id"},
            timeout=15,
        )
        data = resp.json() if resp.content else {}
        name = str(((data.get("data") or {}).get("user") or {}).get("name") or "").strip()
        if name:
            return name
    except Exception:
        logger.exception("lark bridge name lookup failed")
    return fallback


def maybe_handle_lark_bridge(
    config: Any, event_data: dict[str, Any]
) -> dict[str, Any] | None:
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
    sender_id = _sender_open_id(sender)
    allowed = owner_open_ids(config)
    command_id = str(message.get("message_id") or "")
    parent_id = str(message.get("parent_id") or "").strip()
    root_id = str(message.get("root_id") or "").strip()
    chat_id = str(message.get("chat_id") or "")
    is_roy = bool(allowed and sender_id in allowed)

    if is_roy:
        session = find_session_by_bridge(parent_id) or find_session_by_bridge(root_id)
        if session is None:
            return None
    else:
        session = match_inbound(message, sender)
        if session is None:
            return None

    if command_id and not claim_message(command_id):
        return {"ok": True, "bridge": "duplicate"}

    app_id, app_secret = _lark_creds(config)
    if not app_id or not app_secret:
        logger.error("lark bridge missing app credentials")
        return {"ok": False, "bridge": "no_credentials"}
    try:
        token = get_tenant_access_token(app_id, app_secret)
    except Exception:
        logger.exception("lark bridge token failed")
        return {"ok": False, "bridge": "token_failed"}

    roy_chat = str(session.get("roy_chat_id") or "")
    if is_roy:
        if not session_active(session):
            _reply(token, chat_id or roy_chat, "这轮对话已经超过 24 小时。重新 send to 再聊。")
            return {"ok": True, "bridge": "expired"}
        body = (text or "").strip()
        if not body:
            _reply(token, chat_id or roy_chat, "空的，没发出去。")
            return {"ok": True, "bridge": "empty"}
        kind = str(session.get("kind") or "user")
        peer_id = str(session.get("peer_id") or "")
        peer_name = str(session.get("peer_name") or "对方")
        quote_id = str(session.get("last_peer_message_id") or "")
        try:
            if quote_id:
                sent_id = _reply_to_message(token, quote_id, body)
            else:
                sent_id = _send_plain(token, kind, peer_id, body)
        except Exception as exc:
            logger.exception("lark bridge send-back failed")
            if quote_id:
                try:
                    sent_id = _send_plain(token, kind, peer_id, body)
                except Exception as exc2:
                    logger.exception("lark bridge send-back fallback failed")
                    _reply(token, chat_id or roy_chat, f"回给 {peer_name} 失败：{exc2}")
                    return {"ok": False, "bridge": "send_failed"}
            else:
                _reply(token, chat_id or roy_chat, f"回给 {peer_name} 失败：{exc}")
                return {"ok": False, "bridge": "send_failed"}
        log_sent_message(
            message_id=sent_id,
            text=body,
            name=peer_name,
            kind=kind,
            target_id=peer_id,
        )
        _touch(session, outbound_message_id=sent_id)
        logger.info("lark bridge send-back name=%s message=%s", peer_name, sent_id)
        return {"ok": True, "bridge": "sent", "name": peer_name}

    name = str(session.get("peer_name") or "对方")
    group_name = ""
    if str(session.get("kind") or "") == "group":
        group_name = name
        name = _user_name(token, sender_id, "成员")
    push = format_inbound_push(name, text, group_name=group_name)
    dest = roy_chat
    if not dest:
        roy_ids = list(allowed)
        dest_kind, dest_id = ("user", roy_ids[0]) if roy_ids else ("", "")
    else:
        dest_kind, dest_id = "group", dest
    try:
        if dest_kind == "user":
            from bot.workflow_lark_relay import _send_to

            bridge_id = _send_to(token, {"kind": "user", "id": dest_id, "name": "Roy"}, push)
        else:
            from bot.workflow_tech_support import _send_lark_text

            bridge_id = _send_lark_text(token, dest, push)
    except Exception:
        logger.exception("lark bridge push to Roy failed")
        return {"ok": False, "bridge": "push_failed"}
    _touch(
        session,
        bridge_message_id=bridge_id,
        last_peer_message_id=command_id,
    )
    logger.info("lark bridge inbound name=%s to Roy message=%s", name, bridge_id)
    return {"ok": True, "bridge": "pushed", "name": name}
