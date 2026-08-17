"""Workflow: status → live → fetch site logo once into 项目logo (no poller retry on fail).

Per record: HTTP scrape first; on failure Playwright second pass (see project_logo).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.project_logo import fill_logo_for_record, pick_site_url
from bot.workflow_events import append_event
from bot.workflow_form_dispatch import _field_text

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

try:
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=8))

LOGO_EVENTS_FILE = "data/logo_fill_events.jsonl"


def _load_state(path: Path) -> tuple[set[str], dict[str, str]]:
    if not path.exists():
        return set(), {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), {}
    processed = {str(x) for x in (raw.get("processed_record_ids") or [])}
    results = {str(k): str(v) for k, v in (raw.get("results") or {}).items()}
    return processed, results


def _save_state(path: Path, processed: set[str], results: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}
    existing["processed_record_ids"] = sorted(processed)
    existing["results"] = results
    path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_logo_event(
    record_id: str,
    status: str,
    *,
    project_name: str = "",
) -> None:
    """Append one logo attempt for calendar day drill-down (Asia/Shanghai)."""
    now = datetime.now(TZ)
    path = ROOT / LOGO_EVENTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": now.isoformat(timespec="seconds"),
        "day": now.strftime("%Y-%m-%d"),
        "record_id": record_id,
        "project_name": project_name or record_id,
        "status": status,
    }
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("logo-fill: failed appending event for %s", record_id)


def _mark_processed(
    path: Path,
    processed: set[str],
    results: dict[str, str],
    record_id: str,
    status: str,
    *,
    project_name: str = "",
    emit_event: bool = True,
) -> None:
    processed.add(record_id)
    results[record_id] = status
    _save_state(path, processed, results)
    if emit_event and status != "baseline_has_logo":
        _append_logo_event(record_id, status, project_name=project_name)
        if status.startswith("ok"):
            append_event(
                "logo_uploaded_lark",
                "logo_fill",
                project_name=project_name or record_id,
                text=f"{project_name or record_id} 的 Logo 已自动上传到 Lark 表格",
                status="success",
                record_id=record_id,
                result=status,
                icon="image",
            )


async def fill_logo_for_fields(
    config: AppConfig,
    token: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    state_path: Path | None = None,
    processed: set[str] | None = None,
    results: dict[str, str] | None = None,
) -> str:
    """One-shot logo fill for a live record. Marks state even on failure."""
    if not getattr(config, "workflow_logo_fill_enabled", True):
        return "disabled"

    path = state_path or (ROOT / config.workflow_logo_state_file)
    if processed is None or results is None:
        processed, results = _load_state(path)

    if record_id in processed:
        return results.get(record_id, "already_processed")

    project_name = _field_text(fields, config.workflow_project_name_field) or record_id

    if fields.get(config.workflow_logo_field):
        _mark_processed(
            path,
            processed,
            results,
            record_id,
            "already_has_logo",
            project_name=project_name,
        )
        try:
            from bot.metrics import record_logo_outcome

            record_logo_outcome("already_has_logo")
        except Exception:  # noqa: BLE001
            pass
        return "already_has_logo"

    site = pick_site_url(
        fields,
        config.workflow_live_link_field,
        config.workflow_project_link_field,
    )
    if not site:
        _mark_processed(
            path,
            processed,
            results,
            record_id,
            "no_url",
            project_name=project_name,
        )
        try:
            from bot.metrics import record_logo_outcome

            record_logo_outcome("no_url")
        except Exception:  # noqa: BLE001
            pass
        logger.warning("logo-fill skip %r (%s): no project URL", project_name, record_id)
        return "no_url"

    loop = asyncio.get_running_loop()
    try:
        status = await loop.run_in_executor(
            None,
            fill_logo_for_record,
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            record_id,
            project_name,
            site,
            config.workflow_logo_field,
        )
    except Exception as exc:  # noqa: BLE001
        status = f"err:{exc}"
        logger.exception("logo-fill failed for %r (%s)", project_name, record_id)

    # Success or fail: never retry
    _mark_processed(
        path,
        processed,
        results,
        record_id,
        status,
        project_name=project_name,
    )
    try:
        from bot.metrics import record_logo_outcome

        record_logo_outcome(status)
    except Exception:  # noqa: BLE001
        pass
    if status.startswith("ok"):
        logger.info("logo-fill OK %r (%s) %s", project_name, record_id, status)
    else:
        logger.warning(
            "logo-fill FAIL %r (%s) %s — will not retry",
            project_name,
            record_id,
            status,
        )
    return status


async def run_logo_fill_once(config: AppConfig) -> int:
    """Scan live rows missing logo; process each at most once. Returns ok count."""
    if not config.workflow_enabled:
        return 0
    if not getattr(config, "workflow_logo_fill_enabled", True):
        return 0

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("logo-fill skipped: missing LARK_APP_ID / LARK_APP_SECRET")
        return 0

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
    )

    state_path = ROOT / config.workflow_logo_state_file
    processed, results = _load_state(state_path)

    # First run: only baseline live rows that already have a logo.
    # Rows still missing logo are processed once below (success or fail, no retry).
    if config.workflow_baseline_existing_live and not state_path.exists():
        for record in records:
            record_id = str(record.get("record_id") or "")
            fields = record.get("fields") or {}
            status = _field_text(fields, config.workflow_status_field)
            if not record_id or status != config.workflow_trigger_status:
                continue
            if fields.get(config.workflow_logo_field):
                processed.add(record_id)
                results[record_id] = "baseline_has_logo"
        _save_state(state_path, processed, results)
        logger.info(
            "logo-fill baseline: marked %d live project(s) that already have logo",
            len(processed),
        )

    ok_count = 0
    for record in records:
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in processed:
            continue
        fields = record.get("fields") or {}
        status = _field_text(fields, config.workflow_status_field)
        if status != config.workflow_trigger_status:
            continue
        result = await fill_logo_for_fields(
            config,
            token,
            record_id,
            fields,
            state_path=state_path,
            processed=processed,
            results=results,
        )
        if result.startswith("ok"):
            ok_count += 1
    return ok_count


async def logo_fill_loop(config: AppConfig) -> None:
    interval = max(int(config.workflow_poll_interval_minutes or 5), 1) * 60
    while True:
        try:
            from bot.metrics import inc

            inc("poll_cycles_run")
            await run_logo_fill_once(config)
        except Exception:  # noqa: BLE001
            logger.exception("logo-fill loop error")
        await asyncio.sleep(interval)
