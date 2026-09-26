"""Watch Lark progress status → live transitions (poll diff, not full form rescan).

Used as a reliable backup when Feishu table automation → HTTP webhook is not
configured yet (or the public tunnel URL drifts).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.workflow_form_dispatch import _field_text
from bot.workflow_live_trigger import _load_progress_records, process_live_project

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


async def _post_watch_hooks(config: AppConfig) -> None:
    try:
        from bot.workflow_live_onboard import drain_pending_roy_notifies

        await drain_pending_roy_notifies(config)
    except Exception:
        logger.exception("live-status-watch: onboard drain failed")
    try:
        from bot.workflow_form_received_notify import run_form_received_notify_once

        await run_form_received_notify_once(config)
    except Exception:
        logger.exception("live-status-watch: form-received notify failed")


def _state_path(config: AppConfig) -> Path:
    raw = getattr(config, "workflow_live_watch_state_file", "") or (
        "data/live_status_watch_state.json"
    )
    return ROOT / raw


def _load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(x) for x in (raw.get("seen_live_record_ids") or []) if str(x)}


def _save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"seen_live_record_ids": sorted(seen)},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


async def run_live_status_watch_once(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> int:
    """Baseline existing live rows on first run; thereafter process new live only."""
    if not config.workflow_enabled:
        return 0
    if not getattr(config, "workflow_live_status_watch_enabled", False):
        return 0

    path = _state_path(config)
    seen = _load_seen(path)
    first_run = not path.exists()

    try:
        _token, records = await _load_progress_records(config)
    except Exception:
        logger.exception("live-status-watch: failed to load Lark records")
        return 0

    # Reuse this snapshot for deploy enter/leave tracking (no second Lark poll).
    if getattr(config, "workflow_deploy_status_watch_enabled", True):
        try:
            from bot.workflow_deploy_status_watch import process_deploy_status_records

            process_deploy_status_records(config, records)
        except Exception:
            logger.exception("live-status-watch: deploy-status piggyback failed")

    if getattr(config, "workflow_kpi_diag_enabled", False):
        try:
            from bot.workflow_kpi_pass_chain import apply_pass_chain_records

            n = apply_pass_chain_records(_token, config, records)
            if n:
                logger.info("live-status-watch: kpi pass-chain wrote %s row(s)", n)
        except Exception:
            logger.exception("live-status-watch: kpi pass-chain piggyback failed")

    live_now: list[tuple[str, str]] = []
    for record in records:
        rid = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        if not rid:
            continue
        if _field_text(fields, config.workflow_status_field) != config.workflow_trigger_status:
            continue
        name = _field_text(fields, config.workflow_project_name_field) or rid
        live_now.append((rid, name))

    live_ids = {rid for rid, _ in live_now}

    if first_run:
        # Do not backfill-spam: only remember current live set.
        _save_seen(path, live_ids)
        logger.info(
            "live-status-watch baseline: marked %d currently-live row(s) (no send)",
            len(live_ids),
        )
        await _post_watch_hooks(config)
        return 0

    newcomers = [(rid, name) for rid, name in live_now if rid not in seen]
    if not newcomers:
        # Drop rows that left live (optional); keep seen growing is fine.
        await _post_watch_hooks(config)
        return 0

    triggered = 0
    for rid, name in newcomers:
        logger.info(
            "live-status-watch new live: %r (%s) → form+logo",
            name,
            rid,
        )
        try:
            outcome = await process_live_project(
                client,
                config,
                scope,
                record_id=rid,
                project_name=name,
                require_live_status=True,
                source="live_status_watch",
            )
            logger.info(
                "live-status-watch done %r form=%s logo=%s err=%s",
                name,
                outcome.get("form"),
                outcome.get("logo"),
                outcome.get("error"),
            )
            triggered += 1
        except Exception:
            logger.exception("live-status-watch failed for %r (%s)", name, rid)
        seen.add(rid)

    # Also remember any live we already knew + newcomers
    seen |= live_ids
    _save_seen(path, seen)
    await _post_watch_hooks(config)
    return triggered


async def live_status_watch_loop(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> None:
    interval = max(int(getattr(config, "workflow_live_status_watch_seconds", 60) or 60), 30)
    # First pass baselines immediately
    try:
        await run_live_status_watch_once(client, config, scope)
    except Exception:
        logger.exception("live-status-watch initial baseline failed")
    while True:
        await asyncio.sleep(interval)
        try:
            await run_live_status_watch_once(client, config, scope)
        except Exception:
            logger.exception("live-status-watch loop error")
