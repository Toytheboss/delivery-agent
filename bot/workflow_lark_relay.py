"""Private-chat command: Roy tells roy's lark agent to forward a message.

Last line must be ``send to <name>``. Everything above it is the body.
People are resolved with the app's user search. Groups are the chats this
bot is already in. One exact match sends; several matches do not.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SEND_TO_RE = re.compile(r"(?is)^send\s+to\s+(.+?)\s*$")
_MENTION_KEY_RE = re.compile(r"@_user_\d+")
_SEEN_LIMIT = 400
_SENT_LIMIT = 200


def parse_relay_command(text: str) -> tuple[str, str] | None:
    """Return (body, target) when the last non-empty line is ``send to``."""
    lines = (text or "").splitlines()
    idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            idx = i
            break
    if idx is None:
        return None
    match = _SEND_TO_RE.match(lines[idx].strip())
    if not match:
        return None
    target = match.group(1).strip()
    body = "\n".join(lines[:idx]).strip()
    if not target or not body:
        return None
    return body, target


def _fold(name: str) -> str:
    return (name or "").strip().casefold()


def mention_users(message: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Map Lark ``@_user_1`` keys to the mentioned person."""
    out: dict[str, dict[str, str]] = {}
    for item in message.get("mentions") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        ident = item.get("id") or {}
        open_id = ""
        if isinstance(ident, dict):
            open_id = str(ident.get("open_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if key and open_id:
            out[key] = {"kind": "user", "id": open_id, "name": name or key}
    return out


def target_from_mentions(
    target: str, mentions: dict[str, dict[str, str]]
) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    """A last line that is only @mentions resolves to those people.

    One person sends directly. Several people do not send.
    """
    keys: list[str] = []
    for key in _MENTION_KEY_RE.findall(target or ""):
        if key not in keys:
            keys.append(key)
    if not keys:
        return None, []
    rest = _MENTION_KEY_RE.sub("", target or "")
    rest = re.sub(r"[\s@()（）]+", "", rest)
    if rest:
        return None, []
    found = [mentions[key] for key in keys if key in mentions]
    if len(found) == 1 and len(keys) == 1:
        return found[0], found
    return None, found


def substitute_mentions(text: str, mentions: dict[str, dict[str, str]]) -> str:
    def repl(match: re.Match[str]) -> str:
        person = mentions.get(match.group(0))
        if not person:
            return match.group(0)
        return "@" + person["name"]

    return _MENTION_KEY_RE.sub(repl, text or "")


def choose_target(users: list[dict[str, str]], groups: list[dict[str, str]], query: str) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    """Pick one person or group. Exact names beat partial ones."""
    needle = _fold(query)
    if not needle:
        return None, []

    def narrow(items: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
        exact = [item for item in items if _fold(item.get("name") or "") == needle]
        if exact:
            return exact, "exact"
        partial = [item for item in items if needle in _fold(item.get("name") or "")]
        return partial, "partial"

    users_hit, user_kind = narrow(users)
    groups_hit, group_kind = narrow(groups)
    if user_kind == "exact" and group_kind != "exact":
        groups_hit = []
    elif group_kind == "exact" and user_kind != "exact":
        users_hit = []
    found = users_hit + groups_hit
    if len(found) == 1:
        return found[0], found
    return None, found


def owner_open_ids(config: Any) -> set[str]:
    ids = {
        str(item).strip()
        for item in (getattr(config, "lark_relay_owner_open_ids", None) or [])
        if str(item).strip()
    }
    extra = os.getenv("LARK_RELAY_OWNER_OPEN_ID", "")
    for part in extra.split(","):
        if part.strip():
            ids.add(part.strip())
    for assignee in getattr(config, "tech_support_assignees", None) or []:
        name = str((assignee or {}).get("name") or "").strip().casefold()
        open_id = str((assignee or {}).get("open_id") or "").strip()
        if open_id and name in {"roy"}:
            ids.add(open_id)
    return ids


def _event_parts(event_data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    message = event_data.get("message") or {}
    sender = event_data.get("sender") or {}
    return message if isinstance(message, dict) else {}, sender if isinstance(sender, dict) else {}


def _sender_open_id(sender: dict[str, Any]) -> str:
    sender_id = sender.get("sender_id") or {}
    if isinstance(sender_id, dict):
        return str(sender_id.get("open_id") or "").strip()
    return ""


def _seen_path() -> Path:
    override = os.getenv("LARK_RELAY_SEEN", "").strip()
    if override:
        return Path(override)
    shared = Path("/opt/botchain-shared/lark_relay_seen.json")
    if shared.parent.is_dir():
        return shared
    return Path("data/lark_relay_seen.json")


def _sent_path() -> Path:
    override = os.getenv("LARK_RELAY_SENT", "").strip()
    if override:
        return Path(override)
    shared = Path("/opt/botchain-shared/lark_relay_sent.json")
    if shared.parent.is_dir():
        return shared
    return Path("data/lark_relay_sent.json")


def load_sent_messages() -> list[dict[str, str]]:
    path = _sent_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or "").strip()
        text = str(item.get("text") or "")
        if not mid:
            continue
        out.append(
            {
                "id": mid,
                "text": text,
                "name": str(item.get("name") or ""),
                "kind": str(item.get("kind") or ""),
                "target_id": str(item.get("target_id") or ""),
            }
        )
    return out


def log_sent_message(
    *,
    message_id: str,
    text: str,
    name: str,
    kind: str,
    target_id: str,
) -> None:
    """Remember an outbound send-to so recall can find private chats."""
    message_id = (message_id or "").strip()
    if not message_id:
        return
    path = _sent_path()
    row = {
        "id": message_id,
        "text": text or "",
        "name": name or "",
        "kind": kind or "",
        "target_id": target_id or "",
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                handle.seek(0)
                raw_text = handle.read()
                try:
                    raw = json.loads(raw_text) if raw_text.strip() else []
                except json.JSONDecodeError:
                    raw = []
                rows = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
                rows = [item for item in rows if str(item.get("id") or "") != message_id]
                rows.append(row)
                handle.seek(0)
                handle.truncate()
                handle.write(json.dumps(rows[-_SENT_LIMIT:], ensure_ascii=False))
                handle.flush()
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        logger.exception("lark relay sent-file failed")


def claim_message(message_id: str) -> bool:
    """True the first time this Lark message is handled."""
    message_id = (message_id or "").strip()
    if not message_id:
        return True
    path = _seen_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                handle.seek(0)
                raw_text = handle.read()
                try:
                    raw = json.loads(raw_text) if raw_text.strip() else []
                except json.JSONDecodeError:
                    raw = []
                seen = [str(item) for item in raw if str(item).strip()] if isinstance(raw, list) else []
                if message_id in seen:
                    return False
                seen.append(message_id)
                handle.seek(0)
                handle.truncate()
                handle.write(json.dumps(seen[-_SEEN_LIMIT:], ensure_ascii=False))
                handle.flush()
                return True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        logger.exception("lark relay seen-file failed")
        return True


def search_users(token: str, query: str) -> list[dict[str, str]]:
    import requests

    from bot.lark_bitable import LARK_API_BASE

    resp = requests.get(
        f"{LARK_API_BASE}/search/v1/user",
        headers={"Authorization": f"Bearer {token}"},
        params={"query": query, "page_size": 20},
        timeout=20,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise RuntimeError(f"user search failed: {resp.status_code} {data.get('code')} {data.get('msg')}")
    users = ((data.get("data") or {}).get("users")) or []
    out = []
    for user in users:
        open_id = str(user.get("open_id") or "").strip()
        name = str(user.get("name") or "").strip()
        if open_id and name:
            out.append({"kind": "user", "id": open_id, "name": name})
    return out


def list_groups(token: str, *, named_only: bool = True) -> list[dict[str, str]]:
    import requests

    from bot.lark_bitable import LARK_API_BASE

    out: list[dict[str, str]] = []
    page_token = ""
    for _ in range(10):
        params: dict[str, Any] = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"{LARK_API_BASE}/im/v1/chats",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=20,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or data.get("code") not in (0, None):
            raise RuntimeError(f"chat list failed: {resp.status_code} {data.get('code')} {data.get('msg')}")
        payload = data.get("data") or {}
        for item in payload.get("items") or []:
            name = str(item.get("name") or "").strip()
            chat_id = str(item.get("chat_id") or "").strip()
            if not chat_id:
                continue
            if named_only and not name:
                continue
            kind = "group" if name else "p2p"
            out.append({"kind": kind, "id": chat_id, "name": name or chat_id})
        if not payload.get("has_more"):
            break
        page_token = str(payload.get("page_token") or "")
        if not page_token:
            break
    return out


def _send_to(token: str, target: dict[str, str], text: str) -> str:
    import requests

    from bot.lark_bitable import LARK_API_BASE

    receive_type = "open_id" if target["kind"] == "user" else "chat_id"
    content = json.dumps({"text": text}, ensure_ascii=False)
    resp = requests.post(
        f"{LARK_API_BASE}/im/v1/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params={"receive_id_type": receive_type},
        json={
            "receive_id": target["id"],
            "msg_type": "text",
            "content": content,
        },
        timeout=30,
    )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400 or data.get("code") not in (0, None):
        raise RuntimeError(f"relay send failed: {resp.status_code} {data.get('code')} {data.get('msg')}")
    return str(((data.get("data") or {}).get("message_id")) or "")


def _reply(token: str, chat_id: str, text: str) -> None:
    from bot.workflow_tech_support import _send_lark_text

    if not chat_id:
        return
    try:
        _send_lark_text(token, chat_id, text)
    except Exception:
        logger.exception("lark relay reply failed")


def _format_candidates(found: list[dict[str, str]]) -> str:
    lines = []
    for item in found[:8]:
        label = "用户" if item.get("kind") == "user" else "群"
        lines.append(f"- {label} {item.get('name')}")
    extra = len(found) - len(lines)
    if extra > 0:
        lines.append(f"- 还有 {extra} 个")
    return "\n".join(lines)


def maybe_handle_lark_relay(config: Any, event_data: dict[str, Any]) -> dict[str, Any] | None:
    """Handle a send-to command. None means this event is not a command."""
    if not getattr(config, "lark_relay_enabled", True):
        return None
    if not isinstance(event_data, dict):
        return None
    message, sender = _event_parts(event_data)
    if not message:
        return None
    if str(sender.get("sender_type") or "").lower() == "app":
        return None
    if str(message.get("chat_type") or "") != "p2p":
        return None

    from bot.workflow_tech_support import _extract_text_from_lark_content, _lark_creds
    from bot.lark_bitable import get_tenant_access_token

    msg_type = str(message.get("message_type") or message.get("msg_type") or "text")
    text = _extract_text_from_lark_content(msg_type, str(message.get("content") or ""))
    parsed = parse_relay_command(text)
    if not parsed:
        return None
    body, target_name = parsed
    mentions = mention_users(message)
    body = substitute_mentions(body, mentions).strip()
    if not body:
        return None

    message_id = str(message.get("message_id") or "")
    if not claim_message(message_id):
        return {"ok": True, "relay": "duplicate"}

    chat_id = str(message.get("chat_id") or "")
    app_id, app_secret = _lark_creds(config)
    if not app_id or not app_secret:
        logger.error("lark relay missing app credentials")
        return {"ok": False, "relay": "no_credentials"}
    try:
        token = get_tenant_access_token(app_id, app_secret)
    except Exception:
        logger.exception("lark relay token failed")
        return {"ok": False, "relay": "token_failed"}

    sender_id = _sender_open_id(sender)
    allowed = owner_open_ids(config)
    if not allowed or sender_id not in allowed:
        _reply(token, chat_id, "这条指令只接受 Roy 的私聊。")
        logger.info("lark relay rejected sender=%s", sender_id)
        return {"ok": True, "relay": "forbidden"}

    direct, mentioned = target_from_mentions(target_name, mentions)
    if direct is not None or mentioned:
        picked, found = direct, mentioned
        user_error = ""
    else:
        query = substitute_mentions(target_name, mentions).lstrip("@").strip()
        user_error = ""
        try:
            users = search_users(token, query)
        except Exception as exc:
            logger.exception("lark relay user search failed")
            users = []
            user_error = str(exc)
        try:
            groups = list_groups(token)
        except Exception:
            logger.exception("lark relay chat list failed")
            groups = []
        picked, found = choose_target(users, groups, query)
        target_name = query
    if picked is None and not found and user_error:
        _reply(token, chat_id, f"没有找到「{target_name}」。按名字找人失败了，群里也没有这个名字。")
        return {"ok": False, "relay": "search_failed"}
    if picked is None:
        if not found:
            _reply(
                token,
                chat_id,
                f"没有找到「{target_name}」。人要在智能体可用范围内，群要智能体已经在里面。",
            )
            return {"ok": True, "relay": "not_found"}
        _reply(token, chat_id, f"找到多个「{target_name}」，没有发送：\n{_format_candidates(found)}")
        return {"ok": True, "relay": "ambiguous", "count": len(found)}

    try:
        sent_id = _send_to(token, picked, body)
    except Exception as exc:
        logger.exception("lark relay send failed")
        _reply(token, chat_id, f"发给「{picked['name']}」失败：{exc}")
        return {"ok": False, "relay": "send_failed"}

    log_sent_message(
        message_id=sent_id,
        text=body,
        name=str(picked.get("name") or ""),
        kind=str(picked.get("kind") or ""),
        target_id=str(picked.get("id") or ""),
    )
    if picked["kind"] == "user":
        note = f"已发给 {picked['name']}"
    else:
        note = f"已发到群「{picked['name']}」"
    _reply(token, chat_id, note)
    logger.info("lark relay sent kind=%s name=%s message=%s", picked["kind"], picked["name"], sent_id)
    return {"ok": True, "relay": "sent", "kind": picked["kind"], "name": picked["name"]}
