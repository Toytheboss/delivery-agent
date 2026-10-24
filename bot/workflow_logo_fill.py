"""Workflow: status → live → fetch site logo once into 项目logo (no retry on fail)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records
from bot.project_logo import (
    download_image,
    fill_logo_for_record,
    pick_site_url,
    write_logo_attachment,
)
from bot.workflow_form_dispatch import _field_text, _normalize_name

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


def logo_fill_on_this_host() -> bool:
    """Site-logo fetch and attachment write run on 审核号 only.

    The delivery-agent install at ``/opt/delivery-agent`` never uploads logos.
    Two hosts writing the same attachment cell appends a duplicate file.
    """
    root = str(ROOT).replace("\\", "/").lower().rstrip("/")
    return root != "/opt/delivery-agent" and not root.startswith(
        "/opt/delivery-agent/"
    )


def logo_fill_allowed(config: Any) -> bool:
    """True when this process may fetch a site logo into the progress table."""
    if not getattr(config, "workflow_logo_fill_enabled", True):
        return False
    return logo_fill_on_this_host()


def _twitter_state_path(config: Any) -> Path:
    raw = str(getattr(config, "workflow_logo_state_file", "") or "data/logo_fill_state.json")
    path = Path(raw)
    name = "logo_twitter_state.json"
    if path.is_absolute():
        return path.with_name(name)
    return ROOT / path.with_name(name)


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
    path.write_text(
        json.dumps(
            {
                "processed_record_ids": sorted(processed),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _mark_processed(
    path: Path,
    processed: set[str],
    results: dict[str, str],
    record_id: str,
    status: str,
) -> None:
    processed.add(record_id)
    results[record_id] = status
    _save_state(path, processed, results)


def upgrade_twitter_avatar_url(url: str) -> list[str]:
    """Prefer 400px X avatars; keep the original URL as fallback."""
    raw = (url or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for src, dst in (("_normal.", "_400x400."), ("_bigger.", "_400x400.")):
        if src in raw:
            out.append(raw.replace(src, dst, 1))
    out.append(raw)
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def fetch_twitter_avatar(profile_url: str) -> tuple[bytes, str] | None:
    """Official X avatar bytes, or None if the account has no usable image."""
    from bot.workflow_kpi1_twitter import _x_bearer, _x_get, twitter_handle_from_url

    handle = twitter_handle_from_url(profile_url)
    if not handle:
        return None
    bearer = _x_bearer()
    if not bearer:
        logger.warning("twitter-logo skip @%s: no X bearer", handle)
        return None
    resp = _x_get(
        f"/2/users/by/username/{handle}",
        bearer,
        params={"user.fields": "profile_image_url"},
    )
    if resp is not None and resp.status_code == 429:
        raise RuntimeError("429 X user lookup rate limited")
    if resp is None or resp.status_code >= 400:
        logger.warning(
            "twitter-logo lookup HTTP %s handle=@%s",
            None if resp is None else resp.status_code,
            handle,
        )
        return None
    try:
        payload = resp.json()
    except ValueError:
        return None
    if payload.get("errors"):
        return None
    url = str(((payload.get("data") or {}).get("profile_image_url") or "")).strip()
    if not url:
        return None
    for candidate in upgrade_twitter_avatar_url(url):
        got = download_image(candidate)
        if got:
            return got
    return None


def fill_logo_from_twitter(
    token: str,
    config: AppConfig,
    record_id: str,
    project_name: str,
    profile_url: str,
    *,
    overwrite: bool = True,
) -> str:
    """Write the X avatar into the progress logo cell."""
    logo = fetch_twitter_avatar(profile_url)
    if not logo:
        return "no_avatar"
    data, fname = logo
    return write_logo_attachment(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        record_id,
        project_name,
        config.workflow_logo_field,
        data,
        fname,
        overwrite=overwrite,
    )


def _wallet_twitter_map(token: str, config: AppConfig) -> dict[str, str]:
    from bot.workflow_kpi1_twitter import wallet_twitter_url
    from bot.workflow_kpi_write import _display_name_key

    app_token = str(getattr(config, "workflow_base_app_token", "") or "").strip()
    wallet_table = str(getattr(config, "workflow_wallet_table_id", "") or "").strip()
    name_field = str(
        getattr(config, "workflow_wallet_name_field", "") or "Project name"
    ).strip()
    if not app_token or not wallet_table:
        return {}
    out: dict[str, str] = {}
    for row in list_records(token, app_token, wallet_table):
        fields = row.get("fields") or {}
        name = _field_text(fields, name_field)
        url = wallet_twitter_url(fields)
        if not name or not url:
            continue
        out[_display_name_key(name)] = url
        key = _normalize_name(name)
        if key:
            out[key] = url
    return out


def _twitter_for_project(twitter_map: dict[str, str], project_name: str) -> str:
    from bot.workflow_kpi_write import _display_name_key

    return (
        twitter_map.get(_display_name_key(project_name))
        or twitter_map.get(_normalize_name(project_name))
        or ""
    )


def apply_twitter_avatar_for_project(
    token: str,
    config: AppConfig,
    project_name: str,
    profile_url: str,
) -> str:
    """Overwrite progress logo with the X avatar as soon as Twitter is submitted."""
    if not logo_fill_allowed(config):
        return "disabled"
    url = (profile_url or "").strip()
    if not url:
        return "no_url"
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
    )
    try:
        rows = list_records(
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("twitter-logo: failed to list progress for %r", project_name)
        return "error"
    from bot.workflow_kpi_write import _display_name_key

    want_exact = _display_name_key(project_name)
    want_norm = _normalize_name(project_name)
    hits: list[tuple[str, str]] = []
    for row in rows:
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        if not rid:
            continue
        name = _field_text(fields, name_field)
        if _display_name_key(name) == want_exact or _normalize_name(name) == want_norm:
            hits.append((rid, name or project_name))
    if not hits:
        return "unmatched"
    path = _twitter_state_path(config)
    processed, results = _load_state(path)
    last = "unmatched"
    for rid, name in hits:
        try:
            last = fill_logo_from_twitter(
                token, config, rid, name, url, overwrite=True
            )
        except Exception as exc:  # noqa: BLE001
            last = f"err:{exc}"
            logger.exception("twitter-logo fill failed for %r (%s)", name, rid)
        if last.startswith("ok") or last == "no_avatar":
            _mark_processed(path, processed, results, rid, last)
        if last.startswith("ok"):
            logger.info("twitter-logo OK %r (%s) %s", name, rid, last)
        else:
            logger.warning("twitter-logo FAIL %r (%s) %s", name, rid, last)
    return last


async def fill_logo_for_fields(
    config: AppConfig,
    token: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    state_path: Path | None = None,
    processed: set[str] | None = None,
    results: dict[str, str] | None = None,
    twitter_url: str = "",
) -> str:
    """One-shot logo fill for a live record. Marks state even on failure."""
    if not logo_fill_allowed(config):
        return "disabled"

    path = state_path or (ROOT / config.workflow_logo_state_file)
    if processed is None or results is None:
        processed, results = _load_state(path)

    if record_id in processed:
        return results.get(record_id, "already_processed")

    project_name = _field_text(fields, config.workflow_project_name_field) or record_id
    loop = asyncio.get_running_loop()
    if twitter_url:
        try:
            status = await loop.run_in_executor(
                None,
                fill_logo_from_twitter,
                token,
                config,
                record_id,
                project_name,
                twitter_url,
            )
        except Exception as exc:  # noqa: BLE001
            status = f"err:{exc}"
            logger.exception("twitter-logo failed for %r (%s)", project_name, record_id)
        tw_path = _twitter_state_path(config)
        tw_done, tw_results = _load_state(tw_path)
        if status.startswith("ok") or status == "no_avatar":
            _mark_processed(tw_path, tw_done, tw_results, record_id, status)
        if status.startswith("ok"):
            _mark_processed(path, processed, results, record_id, status)
            try:
                from bot.metrics import record_logo_outcome

                record_logo_outcome(status)
            except Exception:  # noqa: BLE001
                pass
            logger.info("logo-fill OK %r (%s) twitter %s", project_name, record_id, status)
            return status

    if fields.get(config.workflow_logo_field):
        _mark_processed(path, processed, results, record_id, "already_has_logo")
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
        _mark_processed(path, processed, results, record_id, "no_url")
        try:
            from bot.metrics import record_logo_outcome

            record_logo_outcome("no_url")
        except Exception:  # noqa: BLE001
            pass
        logger.warning("logo-fill skip %r (%s): no project URL", project_name, record_id)
        return "no_url"

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
    _mark_processed(path, processed, results, record_id, status)
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
    if not logo_fill_allowed(config):
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

    twitter_map = await loop.run_in_executor(None, _wallet_twitter_map, token, config)
    ok_count = 0
    for record in records:
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in processed:
            continue
        fields = record.get("fields") or {}
        status = _field_text(fields, config.workflow_status_field)
        if status != config.workflow_trigger_status:
            continue
        project_name = _field_text(fields, config.workflow_project_name_field) or ""
        result = await fill_logo_for_fields(
            config,
            token,
            record_id,
            fields,
            state_path=state_path,
            processed=processed,
            results=results,
            twitter_url=_twitter_for_project(twitter_map, project_name),
        )
        if result.startswith("ok"):
            ok_count += 1
    ok_count += await _catchup_twitter_logos(
        config, token, records, twitter_map, loop
    )
    return ok_count


async def _catchup_twitter_logos(
    config: AppConfig,
    token: str,
    records: list[dict[str, Any]],
    twitter_map: dict[str, str],
    loop: asyncio.AbstractEventLoop,
) -> int:
    """When Twitter is submitted after go-live, overwrite the site logo with the avatar."""
    path = _twitter_state_path(config)
    processed, results = _load_state(path)
    if config.workflow_baseline_existing_live and not path.exists():
        for record in records:
            rid = str(record.get("record_id") or "")
            fields = record.get("fields") or {}
            if not rid:
                continue
            if _field_text(fields, config.workflow_status_field) != config.workflow_trigger_status:
                continue
            name = _field_text(fields, config.workflow_project_name_field)
            if _twitter_for_project(twitter_map, name):
                processed.add(rid)
                results[rid] = "baseline_has_twitter"
        _save_state(path, processed, results)
        logger.info(
            "twitter-logo baseline: marked %d live project(s) that already have Twitter",
            len(processed),
        )
        return 0

    ok_count = 0
    for record in records:
        rid = str(record.get("record_id") or "")
        if not rid or rid in processed:
            continue
        fields = record.get("fields") or {}
        if _field_text(fields, config.workflow_status_field) != config.workflow_trigger_status:
            continue
        name = _field_text(fields, config.workflow_project_name_field) or rid
        url = _twitter_for_project(twitter_map, name)
        if not url:
            continue
        try:
            status = await loop.run_in_executor(
                None,
                fill_logo_from_twitter,
                token,
                config,
                rid,
                name,
                url,
            )
        except Exception as exc:  # noqa: BLE001
            status = f"err:{exc}"
            logger.exception("twitter-logo catch-up failed for %r (%s)", name, rid)
        if status.startswith("ok") or status == "no_avatar":
            _mark_processed(path, processed, results, rid, status)
        if status.startswith("ok"):
            ok_count += 1
            logger.info("twitter-logo catch-up OK %r (%s) %s", name, rid, status)
        else:
            logger.warning("twitter-logo catch-up FAIL %r (%s) %s", name, rid, status)
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
