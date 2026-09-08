"""Alert delivery team on Lark when a TG project asks to verify."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from bot.lark_bitable import get_tenant_access_token
from bot.lark_im import send_text_to_chat

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
TZ = timezone(timedelta(hours=8))

_BRAND_RE = re.compile(r"(?i)^\s*(?:bot\s*chain|botchain|botchian)\s*$")


def _strip_wrap(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'“”":
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


def _state_path(config: Any) -> Path:
    rel = getattr(config, "workflow_verify_alert_state_file", "") or "data/verify_alert_state.json"
    path = Path(rel)
    return path if path.is_absolute() else ROOT / path


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"last_alert": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"last_alert": {}}
    if not isinstance(data, dict):
        return {"last_alert": {}}
    last = data.get("last_alert")
    if not isinstance(last, dict):
        data["last_alert"] = {}
    return data


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_verify_alert_text(
    *,
    project_name: str,
    chat_title: str,
    sender_username: str,
    sender_id: int | None,
    text: str,
    when: datetime | None = None,
    kind: str = "verify",
) -> str:
    when = when or datetime.now(TZ)
    sender = f"@{sender_username}" if sender_username else (str(sender_id) if sender_id else "未知")
    body = (text or "").strip()
    if len(body) > 280:
        body = body[:280].rstrip() + "…"
    if kind == "mainnet_live":
        header = "【主网上线提醒】"
    else:
        header = "【Verify 提醒】"
    return (
        f"{header}\n"
        f"项目：{project_name or '未知项目'}\n"
        f"TG 群：{chat_title or '未知群'}\n"
        f"时间：{when.strftime('%Y-%m-%d %H:%M')} (UTC+8)\n"
        f"发送人：{sender}\n"
        f"原文：{body or '(空)'}"
    )


def maybe_send_verify_alert(
    config: Any,
    *,
    chat_id: int | None,
    chat_title: str,
    sender_id: int | None,
    sender_username: str,
    text: str,
    kind: str = "verify",
) -> dict[str, Any]:
    """Send Lark alert unless cooldown blocks. Never raises."""
    result: dict[str, Any] = {
        "sent": False,
        "skipped": False,
        "reason": "",
        "project_name": project_name_from_chat_title(chat_title),
        "lark_chat_id": "",
    }
    if not bool(getattr(config, "workflow_verify_alert_enabled", False)):
        result["skipped"] = True
        result["reason"] = "disabled"
        return result

    lark_chat_id = str(getattr(config, "workflow_verify_alert_lark_chat_id", "") or "").strip()
    result["lark_chat_id"] = lark_chat_id
    if not lark_chat_id:
        result["skipped"] = True
        result["reason"] = "missing_lark_chat_id"
        logger.warning("verify alert: missing workflow.verify_alert.lark_chat_id")
        return result

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        result["skipped"] = True
        result["reason"] = "missing_lark_credentials"
        logger.warning("verify alert: LARK_APP_ID/SECRET missing")
        return result

    cooldown_h = float(getattr(config, "workflow_verify_alert_cooldown_hours", 6) or 6)
    cooldown_s = max(cooldown_h, 0) * 3600
    state_path = _state_path(config)
    state = _load_state(state_path)
    last_map: dict[str, Any] = state.setdefault("last_alert", {})
    key = str(chat_id or chat_title or "unknown")
    now = time.time()
    try:
        last_ts = float(last_map.get(key) or 0)
    except (TypeError, ValueError):
        last_ts = 0.0
    if cooldown_s > 0 and last_ts and (now - last_ts) < cooldown_s:
        result["skipped"] = True
        result["reason"] = "cooldown"
        logger.info(
            "verify alert cooldown chat=%s remain=%.0fs",
            key,
            cooldown_s - (now - last_ts),
        )
        return result

    result["kind"] = kind or "verify"
    msg = build_verify_alert_text(
        project_name=result["project_name"],
        chat_title=chat_title,
        sender_username=sender_username or "",
        sender_id=sender_id,
        text=text,
        kind=result["kind"],
    )
    try:
        token = get_tenant_access_token(app_id, app_secret)
        send_text_to_chat(token, lark_chat_id, msg)
    except Exception:  # noqa: BLE001
        logger.exception("verify alert: failed sending to %s", lark_chat_id)
        result["skipped"] = True
        result["reason"] = "send_failed"
        return result

    last_map[key] = now
    # prune old keys (>30d)
    cutoff = now - 30 * 86400
    state["last_alert"] = {
        k: v for k, v in last_map.items() if float(v or 0) >= cutoff
    }
    try:
        _save_state(state_path, state)
    except Exception:  # noqa: BLE001
        logger.exception("verify alert: failed saving state")

    result["sent"] = True
    result["reason"] = "sent"
    logger.info(
        "verify alert sent project=%r chat=%s lark=%s",
        result["project_name"],
        key,
        lark_chat_id,
    )
    return result
