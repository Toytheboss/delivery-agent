"""Copy progress「项目链接」http(s) URLs into empty「已上线链接🔗».

Trigger: a newly added progress-table record (not a timed full-table scan).
Filled live-link cells are never overwritten.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, get_record, list_records, update_record
from bot.workflow_form_dispatch import _field_text

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

_HTTP_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

DEFAULT_LIVE_LINK_FIELD = "已上线链接🔗"
DEFAULT_PROJECT_LINK_FIELD = "项目链接"
DEFAULT_SEEN_STATE = "data/progress_record_watch_state.json"


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


def _field_names(config: AppConfig) -> tuple[str, str, str, str, str]:
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
    return app_token, progress_table, live_field, project_field, name_field


def _can_write(config: AppConfig) -> bool:
    if not getattr(config, "workflow_live_link_sync_enabled", True):
        return False
    from bot.workflow_kpi_write import kpi_checks_on_this_host

    return kpi_checks_on_this_host()


def sync_live_link_row(
    config: AppConfig,
    *,
    record_id: str,
    fields: dict[str, Any],
    token: str | None = None,
    dry_run: bool = False,
) -> str:
    """Sync one progress row. Returns action: updated|skipped_filled|skipped_no_url|skipped|error."""
    if not _can_write(config):
        return "skipped"
    rid = (record_id or "").strip()
    if not rid:
        return "skipped"
    app_token, progress_table, live_field, project_field, name_field = _field_names(config)
    if not app_token or not progress_table or not live_field or not project_field:
        return "skipped"
    if not live_link_empty(fields, live_field):
        return "skipped_filled"
    url = extract_http_site_url(fields.get(project_field))
    if not url:
        return "skipped_no_url"
    project = _field_text(fields, name_field) or rid
    if dry_run:
        logger.info(
            "live-link sync DRY-RUN would set %r → %s (%s)",
            project,
            rid,
            url[:80],
        )
        return "updated"
    try:
        if not token:
            app_id = os.getenv("LARK_APP_ID", "").strip()
            app_secret = os.getenv("LARK_APP_SECRET", "").strip()
            if not app_id or not app_secret:
                logger.warning("live-link sync: missing LARK credentials")
                return "error"
            token = get_tenant_access_token(app_id, app_secret)
        update_record(
            token,
            app_token,
            progress_table,
            rid,
            {live_field: _url_field_payload(url)},
        )
        fields[live_field] = _url_field_payload(url)
        logger.info(
            "live-link sync updated project=%r record=%s url=%s",
            project,
            rid,
            url[:100],
        )
        return "updated"
    except Exception:  # noqa: BLE001
        logger.exception("live-link sync failed project=%r record=%s", project, rid)
        return "error"


def sync_live_link_by_record_id(config: AppConfig, record_id: str) -> dict[str, Any]:
    """Fetch one progress row and sync it (webhook / manual)."""
    rid = (record_id or "").strip()
    out: dict[str, Any] = {"ok": False, "record_id": rid, "action": "skipped"}
    if not rid or not _can_write(config):
        return out
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        out["action"] = "error"
        out["error"] = "missing_credentials"
        return out
    app_token, progress_table, _, _, _ = _field_names(config)
    if not app_token or not progress_table:
        out["action"] = "error"
        out["error"] = "not_configured"
        return out
    token = get_tenant_access_token(app_id, app_secret)
    row = get_record(token, app_token, progress_table, rid)
    fields = row.get("fields") or {}
    action = sync_live_link_row(
        config, record_id=rid, fields=fields, token=token
    )
    out["action"] = action
    out["ok"] = action in {"updated", "skipped_filled", "skipped_no_url"}
    return out


def sync_live_links_once(
    config: AppConfig,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Manual / one-shot backfill across rows. Not used as a timed loop."""
    stats = {
        "scanned": 0,
        "with_url": 0,
        "updated": 0,
        "skipped_filled": 0,
        "skipped_no_url": 0,
        "errors": 0,
    }
    if not _can_write(config):
        return stats
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("live-link sync: missing LARK_APP_ID / LARK_APP_SECRET")
        return stats
    app_token, progress_table, _, _, _ = _field_names(config)
    if not app_token or not progress_table:
        return stats
    token = get_tenant_access_token(app_id, app_secret)
    rows = records if records is not None else list_records(token, app_token, progress_table)
    for row in rows:
        stats["scanned"] += 1
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        if not rid:
            continue
        action = sync_live_link_row(
            config, record_id=rid, fields=fields, token=token, dry_run=dry_run
        )
        if action == "updated":
            stats["updated"] += 1
            stats["with_url"] += 1
        elif action == "skipped_filled":
            stats["skipped_filled"] += 1
        elif action == "skipped_no_url":
            stats["skipped_no_url"] += 1
        elif action == "error":
            stats["errors"] += 1
        if limit is not None and stats["updated"] >= limit:
            break
    if stats["updated"] or stats["errors"]:
        logger.info("live-link sync done: %s", stats)
    else:
        logger.debug("live-link sync done: %s", stats)
    return stats


def _seen_path(config: AppConfig) -> Path:
    raw = (
        getattr(config, "workflow_live_link_sync_state_file", "")
        or DEFAULT_SEEN_STATE
    )
    return ROOT / str(raw)


def _load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(x) for x in (raw.get("seen_record_ids") or []) if str(x)}


def _save_seen(path: Path, seen: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"seen_record_ids": sorted(seen)}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def process_new_progress_records(
    config: AppConfig,
    records: list[dict[str, Any]],
) -> dict[str, int]:
    """Baseline existing rows once; sync only newly appeared record ids.

    Reuses an already-loaded progress snapshot — no extra list_records call.
    """
    stats = {"new": 0, "updated": 0, "skipped": 0, "errors": 0}
    if not getattr(config, "workflow_live_link_sync_enabled", True):
        return stats
    if not _can_write(config):
        return stats

    path = _seen_path(config)
    seen = _load_seen(path)
    first_run = not path.exists()
    all_ids = {
        str(row.get("record_id") or "")
        for row in records
        if str(row.get("record_id") or "")
    }

    if first_run:
        _save_seen(path, all_ids)
        logger.info(
            "live-link sync baseline: remembered %d progress row(s) (no write)",
            len(all_ids),
        )
        return stats

    newcomers = [
        row
        for row in records
        if str(row.get("record_id") or "")
        and str(row.get("record_id") or "") not in seen
    ]
    if not newcomers:
        # Keep seen in sync if rows were deleted/added elsewhere.
        if all_ids - seen:
            seen |= all_ids
            _save_seen(path, seen)
        return stats

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    token = ""
    if app_id and app_secret:
        token = get_tenant_access_token(app_id, app_secret)

    for row in newcomers:
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        stats["new"] += 1
        action = sync_live_link_row(
            config, record_id=rid, fields=fields, token=token or None
        )
        if action == "updated":
            stats["updated"] += 1
        elif action == "error":
            stats["errors"] += 1
        else:
            stats["skipped"] += 1
        seen.add(rid)

    seen |= all_ids
    _save_seen(path, seen)
    if stats["new"]:
        logger.info("live-link sync new-rows: %s", stats)
    return stats
