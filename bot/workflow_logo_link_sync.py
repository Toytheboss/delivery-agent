"""Sync wallet-table Project logo URLs into Progress Tracker「项目logo （链接）」.

Source: form submissions land in 项目方钱包地址搜集 (text URL).
Dest: Progress Tracker URL column — fill only when empty (never overwrite).

Runs as a side-effect of form-chase polling, plus a one-shot / manual backfill.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records, update_record
from bot.workflow_form_dispatch import _field_text, _normalize_name

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

DEFAULT_WALLET_LOGO_FIELD = "Project logo"
DEFAULT_WALLET_NAME_FIELD = "Project name"
# Note the intentional space before （ — matches the live Lark column name.
DEFAULT_PROGRESS_LOGO_LINK_FIELD = "项目logo （链接）"


def _extract_url(value: Any) -> str:
    """Pull a usable http(s) URL from a Lark text / url / list cell."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text.split()[0].rstrip("),.;]")
        match = _URL_RE.search(text)
        return match.group(0).rstrip("),.;]") if match else ""
    if isinstance(value, dict):
        for key in ("link", "url", "text", "name"):
            found = _extract_url(value.get(key))
            if found:
                return found
        return ""
    if isinstance(value, list):
        for item in value:
            found = _extract_url(item)
            if found:
                return found
        return ""
    return _extract_url(str(value))


def _url_field_payload(url: str) -> dict[str, str]:
    """Lark Url (type 15) write shape."""
    return {"link": url, "text": url}


def _progress_link_empty(fields: dict[str, Any], field_name: str) -> bool:
    return not _extract_url(fields.get(field_name))


def _build_progress_index(
    records: list[dict[str, Any]],
    name_field: str,
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """normalized name → [(record_id, fields), ...]"""
    index: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        name = _field_text(fields, name_field)
        key = _normalize_name(name)
        if not record_id or not key:
            continue
        index.setdefault(key, []).append((record_id, fields))
    return index


def sync_logo_links_once(
    config: AppConfig,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    """Copy wallet Project logo URLs into empty progress logo-link cells.

    Returns counts: scanned / with_url / updated / skipped_filled / unmatched / ambiguous / errors.
    """
    stats = {
        "scanned": 0,
        "with_url": 0,
        "updated": 0,
        "skipped_filled": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "errors": 0,
    }
    if not getattr(config, "workflow_logo_link_sync_enabled", True):
        return stats

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("logo-link sync: missing LARK_APP_ID / LARK_APP_SECRET")
        return stats

    app_token = config.workflow_base_app_token
    wallet_table = config.workflow_wallet_table_id
    progress_table = config.workflow_progress_table_id
    wallet_logo_field = (
        getattr(config, "workflow_wallet_logo_field", "") or DEFAULT_WALLET_LOGO_FIELD
    ).strip()
    wallet_name_field = (
        getattr(config, "workflow_wallet_name_field", "") or DEFAULT_WALLET_NAME_FIELD
    ).strip()
    progress_link_field = (
        getattr(config, "workflow_logo_link_field", "")
        or DEFAULT_PROGRESS_LOGO_LINK_FIELD
    ).strip()
    progress_name_field = config.workflow_project_name_field

    token = get_tenant_access_token(app_id, app_secret)
    wallet_rows = list_records(token, app_token, wallet_table)
    progress_rows = list_records(token, app_token, progress_table)
    index = _build_progress_index(progress_rows, progress_name_field)

    for row in wallet_rows:
        stats["scanned"] += 1
        fields = row.get("fields") or {}
        project = _field_text(fields, wallet_name_field)
        url = _extract_url(fields.get(wallet_logo_field))
        if not project or not url:
            continue
        stats["with_url"] += 1
        key = _normalize_name(project)
        matches = index.get(key) or []
        if not matches:
            stats["unmatched"] += 1
            logger.debug("logo-link sync unmatched wallet project=%r", project)
            continue
        if len(matches) > 1:
            stats["ambiguous"] += 1
            logger.info(
                "logo-link sync ambiguous project=%r matches=%d — skip",
                project,
                len(matches),
            )
            continue

        record_id, pfields = matches[0]
        if not _progress_link_empty(pfields, progress_link_field):
            stats["skipped_filled"] += 1
            continue

        if dry_run:
            logger.info(
                "logo-link sync DRY-RUN would set %r → %s (%s)",
                project,
                record_id,
                url[:80],
            )
            stats["updated"] += 1
        else:
            try:
                update_record(
                    token,
                    app_token,
                    progress_table,
                    record_id,
                    {progress_link_field: _url_field_payload(url)},
                )
                # Avoid re-writing same row if wallet has duplicate names later
                pfields[progress_link_field] = _url_field_payload(url)
                stats["updated"] += 1
                logger.info(
                    "logo-link sync updated project=%r record=%s url=%s",
                    project,
                    record_id,
                    url[:100],
                )
            except Exception:  # noqa: BLE001
                stats["errors"] += 1
                logger.exception(
                    "logo-link sync failed project=%r record=%s", project, record_id
                )

        if limit is not None and stats["updated"] >= limit:
            break

    logger.info("logo-link sync done: %s", stats)
    return stats


async def run_logo_link_sync_once(config: AppConfig) -> dict[str, int]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: sync_logo_links_once(config))


async def logo_link_sync_loop(config: AppConfig) -> None:
    """Periodic sync; interval reuses form-chase scan minutes (default 60)."""
    interval = max(
        int(
            getattr(config, "workflow_logo_link_sync_minutes", 0)
            or getattr(config, "workflow_form_chase_scan_minutes", 60)
            or 60
        ),
        5,
    ) * 60
    await asyncio.sleep(min(150, interval))
    while True:
        try:
            stats = await run_logo_link_sync_once(config)
            if stats.get("updated"):
                logger.info(
                    "logo-link sync cycle updated %d row(s)", stats["updated"]
                )
        except Exception:  # noqa: BLE001
            logger.exception("logo-link sync cycle failed")
        await asyncio.sleep(interval)
