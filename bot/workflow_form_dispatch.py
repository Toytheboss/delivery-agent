"""Workflow step 5→6: Lark status live → send Google Form to matched TG group.

Matching order:
1. Optional Lark field TG群ID (if present and valid)
2. Fuzzy match project name ↔ Delivery folder group titles
Manual fallback: group command sends the form in the current chat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records, update_record

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def _load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    sent = raw.get("sent_record_ids") or []
    return {str(x) for x in sent}


def _save_state(path: Path, sent: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"sent_record_ids": sorted(sent)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _field_text(fields: dict[str, Any], name: str) -> str:
    value = fields.get(name)
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or item))
            else:
                parts.append(str(item))
        return " ".join(parts).strip()
    return str(value).strip()


def _parse_chat_id(raw: str) -> int | None:
    text = raw.strip().replace(" ", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _normalize_name(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[\[\]（）()【】{}<>|_·•/\\]+", " ", text)
    # Matching is intentionally case-insensitive and whitespace-insensitive:
    # "Project X", "projectx" and "PROJECT  X" should compare equally.
    return re.sub(r"\s+", "", text)


def build_form_message(config: AppConfig, project_name: str) -> str:
    template = config.workflow_message_template.strip() or (
        "Congrats! {project_name} is live on Delivery Agent Mainnet. "
        "We can now go ahead and push the PR announcement. "
        "It'll be great if you can tweet about this integration — "
        "we'll mention it on our official social media channels and "
        "also share an announcement in our community channels.\n\n"
        "At the same time, could you please fill in this form for "
        "follow-up onboarding? We are collecting the project's address "
        "for future gas return and potential grant provision. Thank you. ⬇️\n"
        "{form_url}"
    )
    return template.format(
        form_url=config.workflow_google_form_url,
        project_name=project_name or "your project",
    )


def match_project_to_chat(
    project_name: str,
    title_by_chat: dict[int, str],
) -> tuple[int | None, str]:
    """Return (chat_id, reason). chat_id is None when unmatched or ambiguous."""
    project = _normalize_name(project_name)
    if not project or len(project) < 2:
        return None, "project name too short"

    candidates: list[tuple[int, str]] = []

    for chat_id, title in title_by_chat.items():
        norm_title = _normalize_name(title)
        if not norm_title:
            continue
        if norm_title == project:
            candidates.append((chat_id, "exact title match"))
        elif project in norm_title or norm_title in project:
            candidates.append((chat_id, "partial title match"))

    if not candidates:
        return None, "no title match"
    # Never guess when more than one group is a candidate.  A false positive
    # would send a form (or mark the wrong Lark row live) in the wrong project
    # chat, so all ambiguous matches must be reviewed manually.
    if len(candidates) > 1:
        ids = [chat_id for chat_id, _ in candidates]
        return None, f"ambiguous title matches: {ids}"
    return candidates[0]


async def build_folder_title_map(
    client: TelegramClient,
    chat_ids: set[int],
    *,
    force_refresh: bool = False,
) -> dict[int, str]:
    """Map chat_id → title with disk+memory cache.

    Avoids resolving ~N groups on every form/wallet poll (main flood source).
    Missing IDs are paced via get_entity; known titles are reused.
    """
    import json
    import time
    from pathlib import Path

    from bot.tg_rate_limit import paced_get_entity, tg_heavy_section

    root = Path(__file__).resolve().parent.parent
    cache_path = root / "data" / "folder_title_cache.json"
    ttl_s = 6 * 3600  # 6h — titles rarely change
    now = time.time()

    cache: dict[str, dict] = {}
    if cache_path.exists() and not force_refresh:
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cache = raw.get("titles") if isinstance(raw.get("titles"), dict) else raw
        except (OSError, json.JSONDecodeError):
            cache = {}

    title_by_chat: dict[int, str] = {}
    missing: list[int] = []
    for chat_id in chat_ids:
        key = str(chat_id)
        entry = cache.get(key)
        if isinstance(entry, dict):
            title = str(entry.get("title") or "").strip()
            ts = float(entry.get("ts") or 0)
            if title and (force_refresh is False) and (now - ts) < ttl_s:
                title_by_chat[chat_id] = title
                continue
        elif isinstance(entry, str) and entry.strip():
            title_by_chat[chat_id] = entry.strip()
            continue
        missing.append(chat_id)

    if missing:
        logger.info(
            "Title cache: resolve %d/%d chat(s) via get_entity",
            len(missing),
            len(chat_ids),
        )
        async with tg_heavy_section():
            for chat_id in missing:
                try:
                    entity = await paced_get_entity(client, chat_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not resolve chat_id=%s: %s", chat_id, exc)
                    continue
                title = getattr(entity, "title", None)
                if title:
                    title_by_chat[chat_id] = str(title)
                    cache[str(chat_id)] = {"title": str(title), "ts": now}

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Drop entries not in current folder set to keep file small
            keep = {str(cid) for cid in chat_ids}
            pruned = {k: v for k, v in cache.items() if k in keep}
            # merge freshly resolved
            for cid, title in title_by_chat.items():
                pruned[str(cid)] = {"title": title, "ts": now}
            cache_path.write_text(
                json.dumps({"titles": pruned}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            logger.exception("Failed to persist folder title cache")

    return title_by_chat


def remember_chat_title(chat_id: int, title: str) -> None:
    """Update title cache when we already know the title (join / auto-add)."""
    import json
    import time
    from pathlib import Path

    title = (title or "").strip()
    if not title:
        return
    root = Path(__file__).resolve().parent.parent
    cache_path = root / "data" / "folder_title_cache.json"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cache = raw.get("titles") if isinstance(raw.get("titles"), dict) else {}
                if not isinstance(cache, dict):
                    cache = {}
        except (OSError, json.JSONDecodeError):
            cache = {}
    cache[str(chat_id)] = {"title": title, "ts": time.time()}
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"titles": cache}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        logger.exception("Failed to update folder title cache")


def is_manual_form_command(text: str, commands: list[str]) -> bool:
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    for cmd in commands:
        c = cmd.strip().lower()
        if c and cleaned == c:
            return True
    return False


async def _mark_sent_in_lark(
    loop: asyncio.AbstractEventLoop,
    token: str,
    config: AppConfig,
    record_id: str,
) -> None:
    if not config.workflow_form_sent_field:
        return
    try:
        await loop.run_in_executor(
            None,
            update_record,
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            record_id,
            {config.workflow_form_sent_field: "已发送"},
        )
    except Exception:
        logger.exception(
            "Form sent but failed to mark Lark field %s on %s",
            config.workflow_form_sent_field,
            record_id,
        )


async def run_form_dispatch_once(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> int:
    """Scan progress table and send Google Form to matched TG groups. Returns sent count."""
    if not config.workflow_enabled:
        return 0
    if not config.workflow_google_form_url:
        logger.warning("workflow.enabled but google_form_url is empty; skip")
        return 0

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("workflow skipped: missing LARK_APP_ID / LARK_APP_SECRET")
        return 0

    if not scope.chat_ids:
        await scope.refresh()

    title_by_chat = await build_folder_title_map(client, scope.chat_ids)
    if not title_by_chat:
        logger.warning("workflow: no resolvable group titles in folder %r", config.folder_name)

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
    )

    state_path = ROOT / config.workflow_state_file
    sent = _load_state(state_path)
    sent_now = 0
    state_dirty = False

    # First run: mark all currently-live rows as already handled (no spam)
    if config.workflow_baseline_existing_live and not state_path.exists():
        for record in records:
            record_id = str(record.get("record_id") or "")
            fields = record.get("fields") or {}
            status = _field_text(fields, config.workflow_status_field)
            if record_id and status == config.workflow_trigger_status:
                sent.add(record_id)
        _save_state(state_path, sent)
        logger.info(
            "Workflow baseline: marked %d existing live project(s) as already handled",
            len(sent),
        )
        return 0

    for record in records:
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in sent:
            continue

        fields = record.get("fields") or {}
        status = _field_text(fields, config.workflow_status_field)
        if status != config.workflow_trigger_status:
            continue

        if config.workflow_form_sent_field:
            already = _field_text(fields, config.workflow_form_sent_field).lower()
            if already in {"true", "yes", "1", "是", "已发送"}:
                sent.add(record_id)
                state_dirty = True
                try:
                    from bot.metrics import record_form_outcome

                    record_form_outcome("already_sent")
                except Exception:  # noqa: BLE001
                    pass
                continue

        project_name = _field_text(fields, config.workflow_project_name_field)
        chat_id: int | None = None
        match_reason = ""

        if config.workflow_tg_chat_id_field:
            chat_raw = _field_text(fields, config.workflow_tg_chat_id_field)
            chat_id = _parse_chat_id(chat_raw)
            if chat_id is not None:
                match_reason = "lark TG群ID field"

        if chat_id is None:
            chat_id, match_reason = match_project_to_chat(project_name, title_by_chat)

        if chat_id is None:
            logger.warning(
                "Skip live project %r (%s): %s — use manual command in TG group",
                project_name,
                record_id,
                match_reason,
            )
            try:
                from bot.metrics import record_form_outcome

                record_form_outcome(f"no_group:{match_reason}")
            except Exception:  # noqa: BLE001
                pass
            continue

        text = build_form_message(config, project_name)
        try:
            await client.send_message(chat_id, text)
        except Exception as exc:
            logger.exception(
                "Failed to send Google Form to chat_id=%s project=%r",
                chat_id,
                project_name,
            )
            try:
                from bot.metrics import record_form_outcome

                record_form_outcome(f"send_failed:{exc}")
            except Exception:  # noqa: BLE001
                pass
            continue

        sent.add(record_id)
        sent_now += 1
        state_dirty = True
        try:
            from bot.metrics import record_form_outcome

            record_form_outcome("sent")
        except Exception:  # noqa: BLE001
            pass
        try:
            from bot.workflow_form_chase import note_form_sent

            note_form_sent(
                config,
                record_id=record_id,
                project_name=project_name,
                chat_id=chat_id,
                source="form_dispatch",
            )
        except Exception:  # noqa: BLE001
            logger.exception("form-chase note failed for %r", project_name)
        logger.info(
            "Sent Google Form to chat_id=%s project=%r record=%s via %s",
            chat_id,
            project_name,
            record_id,
            match_reason,
        )
        await _mark_sent_in_lark(loop, token, config, record_id)

    if state_dirty or not state_path.exists():
        _save_state(state_path, sent)

    return sent_now


async def send_form_manual(
    client: TelegramClient,
    config: AppConfig,
    chat_id: int,
    chat_title: str,
) -> str:
    """Manual fallback: send form in current group; try to mark matching Lark row."""
    if not config.workflow_google_form_url:
        return "Google form URL is not configured (workflow.google_form_url)."

    project_guess = chat_title or "your project"
    text = build_form_message(config, project_guess)
    await client.send_message(chat_id, text)
    try:
        from bot.metrics import record_form_outcome

        record_form_outcome("sent")
    except Exception:  # noqa: BLE001
        pass

    # Best-effort: mark matching live Lark record as sent
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return f"Form sent in this group. (Could not update Lark: missing credentials)"

    loop = asyncio.get_running_loop()
    try:
        token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
        records = await loop.run_in_executor(
            None,
            list_records,
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Manual form sent but Lark lookup failed")
        return f"Form sent. Lark lookup failed: {exc}"

    state_path = ROOT / config.workflow_state_file
    sent = _load_state(state_path)
    title_map = {chat_id: chat_title}
    matched_id = ""

    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        project_name = _field_text(fields, config.workflow_project_name_field)
        matched, reason = match_project_to_chat(project_name, title_map)
        if matched != chat_id:
            continue
        # Prefer live status, but still mark if unique title match
        status = _field_text(fields, config.workflow_status_field)
        matched_id = record_id
        sent.add(record_id)
        await _mark_sent_in_lark(loop, token, config, record_id)
        try:
            from bot.workflow_form_chase import note_form_sent

            note_form_sent(
                config,
                record_id=record_id,
                project_name=project_name,
                chat_id=chat_id,
                source="manual",
            )
        except Exception:  # noqa: BLE001
            logger.exception("form-chase note failed for manual %r", project_name)
        logger.info(
            "Manual form linked to Lark record=%s project=%r (%s, status=%r)",
            record_id,
            project_name,
            reason,
            status,
        )
        break

    _save_state(state_path, sent)
    if matched_id:
        return f"Form sent. Linked Lark record {matched_id}."
    return "Form sent. No unique Lark project matched this group title."


async def form_dispatch_loop(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> None:
    interval = max(config.workflow_poll_interval_minutes, 1) * 60
    while True:
        try:
            from bot.metrics import inc

            inc("poll_cycles_run")
            n = await run_form_dispatch_once(client, config, scope)
            if n:
                logger.info("Form dispatch cycle sent %d message(s)", n)
        except Exception:
            logger.exception("Form dispatch cycle failed")
        await asyncio.sleep(interval)
