"""Immediate actions when a project becomes mainnet-live.

Triggers (no form/logo polling required):
1. Lark webhook / automation HTTP callback
2. TG mark-live keyword (status written, then this runs)
3. Optional one-shot startup catch-up scan
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.workflow_form_dispatch import (
    _field_text,
    _load_state,
    _mark_sent_in_lark,
    _parse_chat_id,
    _save_state,
    build_folder_title_map,
    build_form_message,
    match_project_to_chat,
)
from bot.workflow_logo_fill import fill_logo_for_fields

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope

logger = logging.getLogger(__name__)


async def _load_progress_records(config: AppConfig) -> tuple[str, list[dict[str, Any]]]:
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("Missing LARK_APP_ID / LARK_APP_SECRET")
    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
    )
    return token, records


def _find_record(
    records: list[dict[str, Any]],
    config: AppConfig,
    *,
    record_id: str | None,
    project_name: str | None,
) -> tuple[str, str, dict[str, Any]] | None:
    rid = (record_id or "").strip()
    pname = (project_name or "").strip()
    if rid:
        for record in records:
            if str(record.get("record_id") or "") == rid:
                fields = record.get("fields") or {}
                name = _field_text(fields, config.workflow_project_name_field) or pname
                return rid, name, fields
        return None
    if not pname:
        return None
    hits: list[tuple[str, str, dict[str, Any]]] = []
    target = pname.lower()
    for record in records:
        fields = record.get("fields") or {}
        name = _field_text(fields, config.workflow_project_name_field)
        if not name:
            continue
        if name.lower() == target:
            hits.append((str(record.get("record_id") or ""), name, fields))
    if len(hits) == 1:
        return hits[0]
    return None


async def process_live_project(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
    *,
    record_id: str | None = None,
    project_name: str | None = None,
    require_live_status: bool = True,
    source: str = "event",
    preferred_chat_id: int | None = None,
    preferred_chat_title: str | None = None,
) -> dict[str, Any]:
    """Send Google Form + fill logo for one live project. Idempotent via state files."""
    result: dict[str, Any] = {
        "ok": False,
        "source": source,
        "record_id": record_id,
        "project_name": project_name,
        "form": "skipped",
        "logo": "skipped",
        "error": None,
    }
    if not config.workflow_enabled:
        result["error"] = "workflow disabled"
        return result

    try:
        token, records = await _load_progress_records(config)
    except Exception as exc:  # noqa: BLE001
        logger.exception("live-trigger: failed to load Lark records")
        result["error"] = str(exc)
        return result

    found = _find_record(
        records, config, record_id=record_id, project_name=project_name
    )
    if not found:
        result["error"] = "record not found"
        return result

    rid, name, fields = found
    result["record_id"] = rid
    result["project_name"] = name
    status = _field_text(fields, config.workflow_status_field)
    if require_live_status and status != config.workflow_trigger_status:
        result["error"] = f"status is not live ({status!r})"
        return result

    from pathlib import Path

    root = Path(__file__).resolve().parent.parent

    # --- Google Form ---
    if config.workflow_google_form_url:
        state_path = root / config.workflow_state_file
        sent = _load_state(state_path)
        if rid in sent:
            result["form"] = "already_sent"
        else:
            if not scope.chat_ids:
                await scope.refresh()
            titles = await build_folder_title_map(client, scope.chat_ids)
            # Mark-live from a group outside folder: still target that chat.
            if preferred_chat_id is not None:
                titles[preferred_chat_id] = (
                    (preferred_chat_title or "").strip()
                    or titles.get(preferred_chat_id)
                    or name
                )
            chat_id: int | None = None
            match_reason = ""
            if config.workflow_tg_chat_id_field:
                chat_id = _parse_chat_id(
                    _field_text(fields, config.workflow_tg_chat_id_field)
                )
                if chat_id is not None:
                    match_reason = "lark TG群ID field"
            if chat_id is None and preferred_chat_id is not None:
                matched, reason = match_project_to_chat(
                    name, {preferred_chat_id: titles[preferred_chat_id]}
                )
                if matched == preferred_chat_id:
                    chat_id = preferred_chat_id
                    match_reason = f"preferred chat ({reason})"
            if chat_id is None:
                chat_id, match_reason = match_project_to_chat(name, titles)
            if chat_id is None:
                result["form"] = f"no_group:{match_reason}"
                logger.warning(
                    "live-trigger form skip %r (%s): %s", name, rid, match_reason
                )
            else:
                try:
                    await client.send_message(chat_id, build_form_message(config, name))
                    sent.add(rid)
                    _save_state(state_path, sent)
                    loop = asyncio.get_running_loop()
                    await _mark_sent_in_lark(loop, token, config, rid)
                    try:
                        from bot.workflow_form_chase import note_form_sent

                        note_form_sent(
                            config,
                            record_id=rid,
                            project_name=name,
                            chat_id=chat_id,
                            source=source or "live_trigger",
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("form-chase note failed for %r", name)
                    result["form"] = "sent"
                    result["chat_id"] = chat_id
                    result["chat_title"] = titles.get(chat_id)
                    logger.info(
                        "live-trigger form sent %r (%s) -> %s (%s) via %s",
                        name,
                        rid,
                        chat_id,
                        titles.get(chat_id),
                        source,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("live-trigger form send failed for %r", name)
                    result["form"] = f"send_failed:{exc}"
    else:
        result["form"] = "no_form_url"

    try:
        from bot.metrics import record_form_outcome

        record_form_outcome(str(result.get("form") or ""))
    except Exception:  # noqa: BLE001
        pass

    # --- Logo ---
    if config.workflow_logo_fill_enabled:
        try:
            fields = dict(fields)
            fields[config.workflow_status_field] = config.workflow_trigger_status
            logo_status = await fill_logo_for_fields(config, token, rid, fields)
            result["logo"] = logo_status
        except Exception as exc:  # noqa: BLE001
            logger.exception("live-trigger logo failed for %r", name)
            result["logo"] = f"err:{exc}"
            try:
                from bot.metrics import record_logo_outcome

                record_logo_outcome(result["logo"])
            except Exception:  # noqa: BLE001
                pass
    else:
        result["logo"] = "disabled"

    result["ok"] = result["form"] in {"sent", "already_sent"} or str(
        result["logo"]
    ).startswith("ok")
    return result


async def startup_live_catchup(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> int:
    """One-shot: process live rows not yet form-sent / logo-processed."""
    if not config.workflow_enabled:
        return 0
    try:
        _token, records = await _load_progress_records(config)
    except Exception:
        logger.exception("live-trigger startup catch-up failed to load records")
        return 0

    from pathlib import Path

    from bot.workflow_logo_fill import _load_state as load_logo_state

    root = Path(__file__).resolve().parent.parent
    form_sent = _load_state(root / config.workflow_state_file)
    logo_done, _ = load_logo_state(root / config.workflow_logo_state_file)

    n = 0
    for record in records:
        rid = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        if not rid:
            continue
        if _field_text(fields, config.workflow_status_field) != config.workflow_trigger_status:
            continue
        need_form = bool(config.workflow_google_form_url) and rid not in form_sent
        need_logo = config.workflow_logo_fill_enabled and rid not in logo_done
        if not need_form and not need_logo:
            continue
        await process_live_project(
            client,
            config,
            scope,
            record_id=rid,
            require_live_status=True,
            source="startup_catchup",
        )
        n += 1
        await asyncio.sleep(0.4)
    if n:
        logger.info("live-trigger startup catch-up processed %d project(s)", n)
    return n
