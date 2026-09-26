"""Daily form chase: remind until required wallet fields are filled.

After a project form is sent to TG, track it. Once a day, scan Lark wallet
table. If any of 主网合约 / 推特主页 / logo / 项目介绍 is still empty,
resend a reminder (up to 10 days).
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.workflow_form_dispatch import (
    _field_text,
    _normalize_name,
    match_project_to_chat,
)

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CHASE_FIELDS = [
    "Mainnet Contract Addresss",
    "Link of Project X ( Formerly Twitter) Profile Page",
    "Project logo",
    "A brief introduction of your project",
]

# Same meaning, older Lark column titles
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "Mainnet Contract Addresss": (
        "Mainnet Contract Addresss",
        "Mainnet Contract Address",
        "Contract Addresss/主网合约",
    ),
    "Link of Project X ( Formerly Twitter) Profile Page": (
        "Link of Project X ( Formerly Twitter) Profile Page",
        "Project X ( Formerly Twitter) Profile Page",
        "Project X ( Formly Twitter) Profile Page",
        "Project X ( Formely Twitter) Profile Page",
    ),
}


def _state_path(config: AppConfig) -> Path:
    return ROOT / str(
        getattr(config, "workflow_form_chase_state_file", "data/form_chase_state.json")
    )


def _empty_state() -> dict[str, Any]:
    return {"projects": {}}


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    if not isinstance(raw, dict):
        return _empty_state()
    projects = raw.get("projects")
    if not isinstance(projects, dict):
        raw["projects"] = {}
    return raw


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _chase_fields(config: AppConfig) -> list[str]:
    raw = getattr(config, "workflow_form_chase_fields", None) or DEFAULT_CHASE_FIELDS
    out = [str(x).strip() for x in raw if str(x).strip()]
    return out or list(DEFAULT_CHASE_FIELDS)


def field_is_filled(fields: dict[str, Any], name: str) -> bool:
    """True when Lark cell has usable content (text / link / attachment)."""
    keys = _FIELD_ALIASES.get(name, (name,))
    return any(_value_is_filled(fields.get(key)) for key in keys)


def _value_is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, dict):
        if value.get("file_token") or value.get("url") or value.get("link"):
            return True
        text = str(value.get("text") or value.get("name") or "").strip()
        return bool(text)
    if isinstance(value, list):
        return any(_value_is_filled(item) for item in value)
    return bool(str(value).strip())


def count_filled_fields(fields: dict[str, Any], names: list[str]) -> int:
    return sum(1 for n in names if field_is_filled(fields, n))


def missing_fields(fields: dict[str, Any], names: list[str]) -> list[str]:
    return [n for n in names if not field_is_filled(fields, n)]


# Lark column → wording closer to the Google Form questions
_FIELD_LABELS = {
    "Project name": "Project Name",
    "A brief introduction of your project": "A brief introduction of your project",
    "Link of Project X ( Formerly Twitter) Profile Page": "Project X / Twitter profile page",
    "Project X ( Formerly Twitter) Profile Page": "Project X / Twitter profile page",
    "Project X ( Formly Twitter) Profile Page": "Project X / Twitter profile page",
    "Project logo": "Project logo",
    "Mainnet Contract Addresss": "Mainnet Contract Address",
    "Contract Addresss/主网合约": "Mainnet Contract Address",  # legacy
    "Treasury Address": "Treasury Address",
    "Fee Collector / Revenue Wallet Address": "Fee Collector / Revenue Wallet Address",
}


def field_label(name: str) -> str:
    return _FIELD_LABELS.get(name, name)


def format_missing_list(names: list[str]) -> str:
    labels = [field_label(n) for n in names]
    if not labels:
        return "(none)"
    return "\n".join(f"• {x}" for x in labels)


def build_chase_message(
    config: AppConfig,
    project_name: str,
    missing: list[str] | None = None,
) -> str:
    missing = list(missing or [])
    missing_block = format_missing_list(missing)
    missing_inline = ", ".join(field_label(n) for n in missing) or "required fields"
    template = (
        getattr(config, "workflow_form_chase_message_template", "") or ""
    ).strip()
    if not template:
        template = (
            "Hi {project_name} team — friendly reminder to finish this form. "
            "We use it for website showcase / future gas rebates / potential "
            "grant support.\n\n"
            "Still missing:\n"
            "{missing_fields}\n\n"
            "Please fill these in when you can:\n"
            "{form_url}\n\n"
            "Thanks!"
        )
    try:
        return template.format(
            form_url=config.workflow_google_form_url,
            project_name=project_name or "your project",
            missing_fields=missing_block,
            missing_fields_inline=missing_inline,
        )
    except (KeyError, ValueError):
        return (
            f"Hi {project_name or 'your project'} team — friendly reminder to "
            f"finish this form. We use it for website showcase / future gas "
            f"rebates / potential grant support.\n\n"
            f"Still missing:\n"
            f"{missing_block}\n\n"
            f"Please fill these in when you can:\n"
            f"{config.workflow_google_form_url}\n\n"
            f"Thanks!"
        )


def _shared_chase_inbox() -> Path | None:
    parent = Path("/opt/botchain-shared")
    if not parent.is_dir():
        return None
    return parent / "form_chase_inbox.json"


def enqueue_shared_chase(
    inbox: Path,
    *,
    record_id: str,
    project_name: str,
    chat_id: int,
    source: str = "",
    now: float | None = None,
) -> None:
    """Let the chasing bot pick up a form send that this account does not track."""
    rid = str(record_id or "").strip()
    if not rid:
        return
    now = time.time() if now is None else now
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with inbox.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        projects = data.get("projects")
        if not isinstance(projects, dict):
            projects = {}
            data["projects"] = projects
        existing = projects.get(rid)
        if not (isinstance(existing, dict) and existing.get("first_sent_at")):
            projects[rid] = {
                "project_name": project_name or "",
                "chat_id": int(chat_id),
                "first_sent_at": now,
                "last_sent_at": now,
                "reminders_sent": 0,
                "done": False,
                "source": source or "",
            }
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        handle.flush()


def absorb_shared_chase_inbox(config: AppConfig, *, inbox: Path | None = None) -> int:
    """Copy form sends the other bot queued into this bot's chase file."""
    if not getattr(config, "workflow_form_chase_enabled", False):
        return 0
    inbox = _shared_chase_inbox() if inbox is None else inbox
    if inbox is None or not inbox.exists():
        return 0
    with inbox.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read()
        try:
            incoming = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            incoming = {}
        projects_in = incoming.get("projects") if isinstance(incoming, dict) else None
        if not isinstance(projects_in, dict) or not projects_in:
            return 0
        path = _state_path(config)
        state = _load_state(path)
        local = state.setdefault("projects", {})
        merged = 0
        for rid, meta in projects_in.items():
            if not isinstance(meta, dict):
                continue
            existing = local.get(rid)
            if isinstance(existing, dict) and existing.get("first_sent_at"):
                continue
            local[rid] = meta
            merged += 1
        if merged:
            _save_state(path, state)
            logger.info("form-chase absorbed %d shared send(s)", merged)
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"projects": {}}, ensure_ascii=False, indent=2) + "\n")
        handle.flush()
        return merged


def note_form_sent(
    config: AppConfig,
    *,
    record_id: str,
    project_name: str,
    chat_id: int,
    source: str = "",
) -> None:
    """Register / refresh chase tracking when a Google Form is first sent."""
    if not getattr(config, "workflow_form_chase_enabled", False):
        inbox = _shared_chase_inbox()
        if inbox is not None:
            enqueue_shared_chase(
                inbox,
                record_id=record_id,
                project_name=project_name,
                chat_id=chat_id,
                source=source,
            )
        return
    rid = str(record_id or "").strip()
    if not rid or chat_id is None:
        return
    path = _state_path(config)
    state = _load_state(path)
    projects: dict[str, Any] = state.setdefault("projects", {})
    now = time.time()
    existing = projects.get(rid)
    if isinstance(existing, dict) and existing.get("done"):
        return
    if isinstance(existing, dict) and existing.get("first_sent_at"):
        # Keep original first_sent_at; refresh chat/name if needed.
        existing["project_name"] = project_name or existing.get("project_name") or ""
        existing["chat_id"] = int(chat_id)
        existing["last_sent_at"] = float(existing.get("last_sent_at") or now)
        existing.setdefault("reminders_sent", 0)
        existing.setdefault("done", False)
        if source:
            existing["source"] = source
    else:
        projects[rid] = {
            "project_name": project_name or "",
            "chat_id": int(chat_id),
            "first_sent_at": now,
            "last_sent_at": now,
            "reminders_sent": 0,
            "done": False,
            "source": source or "",
        }
    _save_state(path, state)
    logger.info(
        "form-chase tracked record=%s project=%r chat_id=%s source=%s",
        rid,
        project_name,
        chat_id,
        source or "-",
    )


def _find_wallet_fields(
    wallet_records: list[dict[str, Any]],
    project_name: str,
    fields_needed: list[str] | None = None,
) -> dict[str, Any] | None:
    """Pick wallet row for project; if duplicates, prefer the most complete form."""
    want = _normalize_name(project_name)
    if not want:
        return None
    needed = list(fields_needed or DEFAULT_CHASE_FIELDS)
    exact_rows: list[dict[str, Any]] = []
    partial_rows: list[dict[str, Any]] = []
    for record in wallet_records:
        fields = record.get("fields") or {}
        name = _field_text(fields, "Project name")
        nn = _normalize_name(name)
        if not nn:
            continue
        if nn == want:
            exact_rows.append(fields)
        elif want in nn or nn in want:
            partial_rows.append(fields)

    def _best(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        if len(rows) == 1:
            return rows[0]
        # Duplicate display names (e.g. "Bot Launch" vs "BotLaunch") must not
        # lock onto an incomplete older row while a complete one also exists.
        return max(rows, key=lambda f: count_filled_fields(f, needed))

    return _best(exact_rows) or _best(partial_rows)


def _load_title_cache() -> dict[int, str]:
    path = ROOT / "data" / "folder_title_cache.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    entries = raw.get("titles") if isinstance(raw.get("titles"), dict) else raw
    out: dict[int, str] = {}
    if not isinstance(entries, dict):
        return out
    for key, entry in entries.items():
        try:
            chat_id = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(entry, dict):
            title = str(entry.get("title") or "").strip()
        else:
            title = str(entry or "").strip()
        if title:
            out[chat_id] = title
    return out


def _chase_chat_still_matches(
    project_name: str, chat_id: int, titles: dict[int, str]
) -> tuple[bool, str]:
    """False when this TG group is a longer/different product than the Lark name."""
    title = str(titles.get(chat_id) or "").strip()
    if not title:
        return True, "title_unknown"
    matched, reason = match_project_to_chat(project_name, {chat_id: title})
    if matched == chat_id:
        return True, reason
    return False, reason or "weak_title_match"


async def run_form_chase_once(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope | None = None,
) -> int:
    """Scan tracked form sends; remind once after 24h if wallet data incomplete."""
    if not getattr(config, "workflow_form_chase_enabled", False):
        return 0
    if not config.workflow_enabled or not config.workflow_google_form_url:
        return 0

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("form-chase skipped: missing LARK credentials")
        return 0

    after_hours = max(float(getattr(config, "workflow_form_chase_after_hours", 24) or 24), 1.0)
    min_filled = max(int(getattr(config, "workflow_form_chase_min_filled", 4) or 4), 1)
    max_reminders = max(int(getattr(config, "workflow_form_chase_max_reminders", 10) or 10), 0)
    fields_needed = _chase_fields(config)
    if max_reminders <= 0:
        return 0

    absorb_shared_chase_inbox(config)
    path = _state_path(config)
    state = _load_state(path)
    projects: dict[str, Any] = state.get("projects") or {}
    if not projects:
        return 0

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    wallet_records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_wallet_table_id,
    )

    now = time.time()
    threshold = after_hours * 3600.0
    reminded = 0
    dirty = False
    titles = _load_title_cache()

    for rid, meta in list(projects.items()):
        if not isinstance(meta, dict):
            continue
        if meta.get("done"):
            continue
        project_name = str(meta.get("project_name") or "").strip()
        try:
            chat_id = int(meta.get("chat_id"))
        except (TypeError, ValueError):
            continue
        ok_chat, chat_reason = _chase_chat_still_matches(project_name, chat_id, titles)
        if not ok_chat:
            meta["done"] = True
            meta["cancelled"] = True
            meta["cancel_reason"] = f"wrong_chat:{chat_reason}"
            meta["completed_at"] = now
            dirty = True
            logger.warning(
                "form-chase cancelled record=%s project=%r chat_id=%s title=%r reason=%s",
                rid,
                project_name,
                chat_id,
                titles.get(chat_id),
                chat_reason,
            )
            continue
        try:
            first_sent_at = float(meta.get("first_sent_at") or 0)
        except (TypeError, ValueError):
            first_sent_at = 0.0
        reminders = int(meta.get("reminders_sent") or 0)

        wallet_fields = _find_wallet_fields(
            wallet_records, project_name, fields_needed=fields_needed
        )
        filled_names = [
            n for n in fields_needed if field_is_filled(wallet_fields or {}, n)
        ]
        filled = len(filled_names)
        missing = missing_fields(wallet_fields or {}, fields_needed)
        if filled >= min_filled:
            meta["done"] = True
            meta["filled_count"] = filled
            meta["completed_at"] = now
            dirty = True
            logger.info(
                "form-chase complete record=%s project=%r filled=%d/%d",
                rid,
                project_name,
                filled,
                len(fields_needed),
            )
            continue

        if reminders >= max_reminders:
            continue
        if first_sent_at <= 0 or (now - first_sent_at) < threshold:
            continue

        # Also gate on last reminder spacing (same after_hours between reminders)
        try:
            last_sent_at = float(meta.get("last_sent_at") or first_sent_at)
        except (TypeError, ValueError):
            last_sent_at = first_sent_at
        if reminders > 0 and (now - last_sent_at) < threshold:
            continue

        text = build_chase_message(config, project_name, missing=missing)
        try:
            await client.send_message(chat_id, text)
        except Exception:
            logger.exception(
                "form-chase send failed record=%s project=%r chat_id=%s",
                rid,
                project_name,
                chat_id,
            )
            continue

        meta["reminders_sent"] = reminders + 1
        meta["last_sent_at"] = now
        meta["last_filled_count"] = filled
        meta["last_missing_fields"] = missing
        dirty = True
        reminded += 1
        logger.info(
            "form-chase reminded record=%s project=%r chat_id=%s "
            "filled=%d/%d missing=%s reminder=%d/%d",
            rid,
            project_name,
            chat_id,
            filled,
            len(fields_needed),
            missing,
            reminders + 1,
            max_reminders,
        )
        try:
            from bot.metrics import record_form_outcome

            record_form_outcome("chase_reminded")
        except Exception:  # noqa: BLE001
            pass

    if dirty:
        state["projects"] = projects
        _save_state(path, state)
    return reminded


async def form_chase_loop(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope | None = None,
) -> None:
    """Run form chase once per day at the same hour as the wallet Lark digest."""
    from bot.workflow_lark_wallet_group import (
        TZ,
        _digest_hour,
        _seconds_until_next_hour,
    )

    hour = _digest_hour(config)
    logger.info(
        "form-chase scheduled daily at %02d:00 Asia/Shanghai (with wallet digest)",
        hour,
    )
    # Wait for the next digest window so restarts do not re-chase midday.
    await asyncio.sleep(await _seconds_until_next_hour(hour) + 1)
    while True:
        path = _state_path(config)
        state = _load_state(path)
        day_key = datetime.now(TZ).strftime("%Y-%m-%d")
        if state.get("last_chase_date") == day_key:
            logger.info("form-chase already ran for %s — skip", day_key)
        else:
            try:
                n = await run_form_chase_once(client, config, scope)
                if n:
                    logger.info("form-chase cycle sent %d reminder(s)", n)
                state = _load_state(path)
                state["last_chase_date"] = day_key
                _save_state(path, state)
            except Exception:
                logger.exception("form-chase cycle failed")
        await asyncio.sleep(await _seconds_until_next_hour(hour) + 1)
