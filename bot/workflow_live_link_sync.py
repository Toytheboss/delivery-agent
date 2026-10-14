"""Copy progress「项目链接」http(s) URLs into empty「已上线链接🔗」.

When BD adds a project (or an older row still has an empty live link), take the
first http:// or https:// URL from 项目链接 and write it into 已上线链接.
Filled live-link cells are never overwritten.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records, update_record
from bot.workflow_form_dispatch import _field_text

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

_HTTP_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

DEFAULT_LIVE_LINK_FIELD = "已上线链接🔗"
DEFAULT_PROJECT_LINK_FIELD = "项目链接"


def extract_http_site_url(value: Any) -> str:
    """First http(s) URL in a Lark cell, kept as written (no scheme rewrite)."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        match = _HTTP_URL_RE.search(text)
        return match.group(0).rstrip("),.;]>\"'") if match else ""
    if isinstance(value, dict):
        for key in ("link", "url", "text", "name"):
            found = extract_http_site_url(value.get(key))
            if found:
                return found
        return ""
    if isinstance(value, list):
        for item in value:
            found = extract_http_site_url(item)
            if found:
                return found
        return ""
    return extract_http_site_url(str(value))


def _url_field_payload(url: str) -> dict[str, str]:
    return {"link": url, "text": url}


def live_link_empty(fields: dict[str, Any], live_field: str) -> bool:
    return not extract_http_site_url(fields.get(live_field))


def sync_live_links_once(
    config: AppConfig,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Fill empty 已上线链接 from 项目链接 http(s) URLs.

    Returns counts: scanned / with_url / updated / skipped_filled / skipped_no_url / errors.
    """
    stats = {
        "scanned": 0,
        "with_url": 0,
        "updated": 0,
        "skipped_filled": 0,
        "skipped_no_url": 0,
        "errors": 0,
    }
    if not getattr(config, "workflow_live_link_sync_enabled", True):
        return stats
    # Only the audit host writes progress live links (avoid double writes).
    from bot.workflow_kpi_write import kpi_checks_on_this_host

    if not kpi_checks_on_this_host():
        return stats

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("live-link sync: missing LARK_APP_ID / LARK_APP_SECRET")
        return stats

    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    progress_table = str(getattr(config, "workflow_progress_table_id", "") or "").strip()
    live_field = str(
        getattr(config, "workflow_live_link_field", "") or DEFAULT_LIVE_LINK_FIELD
    ).strip()
    project_field = str(
        getattr(config, "workflow_project_link_field", "") or DEFAULT_PROJECT_LINK_FIELD
    ).strip()
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
    ).strip()
    if not app_token or not progress_table or not live_field or not project_field:
        logger.warning("live-link sync: progress table / link fields not configured")
        return stats

    token = get_tenant_access_token(app_id, app_secret)
    rows = records
    if rows is None:
        rows = list_records(token, app_token, progress_table)

    for row in rows:
        stats["scanned"] += 1
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        if not rid:
            continue
        if not live_link_empty(fields, live_field):
            stats["skipped_filled"] += 1
            continue
        url = extract_http_site_url(fields.get(project_field))
        if not url:
            stats["skipped_no_url"] += 1
            continue
        stats["with_url"] += 1
        project = _field_text(fields, name_field) or rid

        if dry_run:
            logger.info(
                "live-link sync DRY-RUN would set %r → %s (%s)",
                project,
                rid,
                url[:80],
            )
            stats["updated"] += 1
        else:
            try:
                update_record(
                    token,
                    app_token,
                    progress_table,
                    rid,
                    {live_field: _url_field_payload(url)},
                )
                fields[live_field] = _url_field_payload(url)
                stats["updated"] += 1
                logger.info(
                    "live-link sync updated project=%r record=%s url=%s",
                    project,
                    rid,
                    url[:100],
                )
            except Exception:  # noqa: BLE001
                stats["errors"] += 1
                logger.exception(
                    "live-link sync failed project=%r record=%s", project, rid
                )

        if limit is not None and stats["updated"] >= limit:
            break

    if stats["updated"] or stats["errors"]:
        logger.info("live-link sync done: %s", stats)
    else:
        logger.debug("live-link sync done: %s", stats)
    return stats


async def run_live_link_sync_once(
    config: AppConfig,
    *,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: sync_live_links_once(config, records=records)
    )


async def live_link_sync_loop(config: AppConfig) -> None:
    """Backfill on start, then rescan on an interval for newly added rows."""
    minutes = int(getattr(config, "workflow_live_link_sync_minutes", 5) or 5)
    interval = max(minutes, 1) * 60
    logger.info(
        "live-link sync enabled (项目链接 → %r, every %d min, run on start)",
        getattr(config, "workflow_live_link_field", DEFAULT_LIVE_LINK_FIELD),
        max(minutes, 1),
    )
    while True:
        try:
            stats = await run_live_link_sync_once(config)
            if stats.get("updated"):
                logger.info(
                    "live-link sync cycle updated %d row(s)", stats["updated"]
                )
        except Exception:  # noqa: BLE001
            logger.exception("live-link sync cycle failed")
        await asyncio.sleep(interval)
