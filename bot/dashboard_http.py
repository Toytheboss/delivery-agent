"""HTTP routes for Delivery dashboard + settings (served on webhook port)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from bot.config_loader import AppConfig
    from bot.knowledge import KnowledgeBase

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static" / "dashboard"

_build_lock = asyncio.Lock()


def dashboard_token(config: AppConfig) -> str:
    return (
        os.getenv("DASHBOARD_TOKEN", "").strip()
        or str(getattr(config, "dashboard_token", "") or "").strip()
    )


def dashboard_enabled(config: AppConfig) -> bool:
    return bool(getattr(config, "dashboard_enabled", True))


def _extract_token(request: web.Request) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    q = (request.rel_url.query.get("token") or "").strip()
    if q:
        return q
    return (request.headers.get("X-Dashboard-Token") or "").strip()


def _authorized(request: web.Request, config: AppConfig) -> bool:
    expected = dashboard_token(config)
    if not expected:
        return False
    return _extract_token(request) == expected


def _html_page(name: str) -> Path:
    return STATIC_DIR / name


async def _ensure_snapshot(config: AppConfig, *, force: bool = False) -> dict[str, Any]:
    from bot.dashboard_snapshot import (
        load_dashboard_snapshot,
        snapshot_age_seconds,
        write_dashboard_snapshot,
    )

    refresh_s = max(int(getattr(config, "dashboard_refresh_minutes", 60) or 60), 5) * 60
    age = snapshot_age_seconds(config)
    data = load_dashboard_snapshot(config)
    if force or data is None or age is None or age > refresh_s:
        async with _build_lock:
            age2 = snapshot_age_seconds(config)
            data2 = load_dashboard_snapshot(config)
            if force or data2 is None or age2 is None or age2 > refresh_s:
                loop = asyncio.get_running_loop()
                path = await loop.run_in_executor(
                    None, write_dashboard_snapshot, config
                )
                logger.info("dashboard snapshot written: %s", path)
                data = load_dashboard_snapshot(config) or {}
            else:
                data = data2 or {}
    return data or {}


def register_dashboard_routes(
    app: web.Application,
    config: AppConfig,
    *,
    kb: KnowledgeBase | None = None,
) -> None:
    if not dashboard_enabled(config):
        return
    if not dashboard_token(config):
        logger.warning(
            "dashboard enabled but DASHBOARD_TOKEN / dashboard.token empty — routes not registered"
        )
        return

    app["dashboard_config"] = config
    app["dashboard_kb"] = kb

    async def require_auth(request: web.Request) -> web.Response | None:
        if not _authorized(request, app["dashboard_config"]):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        return None

    async def api_snapshot(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied:
            return denied
        force = (request.rel_url.query.get("refresh") or "") in {"1", "true", "yes"}
        data = await _ensure_snapshot(app["dashboard_config"], force=force)
        return web.json_response(data)

    async def api_day(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied:
            return denied
        day = (request.rel_url.query.get("date") or "").strip()
        if not day:
            return web.json_response({"ok": False, "error": "date required"}, status=400)
        from bot.dashboard_snapshot import build_day_detail

        loop = asyncio.get_running_loop()
        try:
            detail = await loop.run_in_executor(
                None, build_day_detail, app["dashboard_config"], day
            )
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            logger.exception("dashboard day detail failed")
            return web.json_response({"ok": False, "error": str(exc)}, status=500)
        return web.json_response(detail)

    async def api_settings_get(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied:
            return denied
        from bot.dashboard_settings import get_settings_view

        return web.json_response(get_settings_view(app["dashboard_config"]))

    async def api_settings_put(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied:
            return denied
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)
        updates = body.get("values") if isinstance(body, dict) else None
        if not isinstance(updates, dict):
            updates = body if isinstance(body, dict) else {}
        from bot.dashboard_settings import apply_settings_to_config, get_settings_view

        applied = apply_settings_to_config(app["dashboard_config"], updates)
        return web.json_response(
            {"ok": True, "applied": applied, "settings": get_settings_view(app["dashboard_config"])}
        )

    async def api_learned_get(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied:
            return denied
        from bot.dashboard_settings import list_learned

        return web.json_response({"items": list_learned(app["dashboard_config"])})

    async def api_learned_post(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied:
            return denied
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)
        content = str((body or {}).get("content") or "")
        question = str((body or {}).get("related_question") or "")
        sync_lark = bool((body or {}).get("sync_lark", False))
        from bot.dashboard_settings import create_learned_note

        try:
            created = create_learned_note(
                app["dashboard_config"],
                content=content,
                related_question=question,
                sync_lark=sync_lark,
            )
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        kb_obj = app.get("dashboard_kb")
        if kb_obj is not None:
            try:
                kb_obj.reload()
            except Exception:  # noqa: BLE001
                logger.exception("kb reload after learn failed")
        return web.json_response({"ok": True, **created})

    async def api_learned_delete(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied:
            return denied
        name = (request.match_info.get("name") or "").strip()
        from bot.dashboard_settings import delete_learned_note

        try:
            ok = delete_learned_note(app["dashboard_config"], name)
        except ValueError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        kb_obj = app.get("dashboard_kb")
        if ok and kb_obj is not None:
            try:
                kb_obj.reload()
            except Exception:  # noqa: BLE001
                logger.exception("kb reload after delete failed")
        return web.json_response({"ok": ok})

    async def api_kb_reload(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied:
            return denied
        kb_obj = app.get("dashboard_kb")
        if kb_obj is None:
            return web.json_response({"ok": False, "error": "kb unavailable"}, status=503)
        try:
            count = kb_obj.reload()
        except Exception as exc:  # noqa: BLE001
            logger.exception("kb reload failed")
            return web.json_response({"ok": False, "error": str(exc)}, status=500)
        return web.json_response({"ok": True, "chunks": count})

    async def page_index(request: web.Request) -> web.Response:
        if not _authorized(request, app["dashboard_config"]):
            return web.Response(text="unauthorized — add ?token=", status=401)
        path = _html_page("index.html")
        if not path.is_file():
            return web.Response(text="index.html missing", status=500)
        return web.FileResponse(path)

    async def page_settings(request: web.Request) -> web.Response:
        if not _authorized(request, app["dashboard_config"]):
            return web.Response(text="unauthorized — add ?token=", status=401)
        path = _html_page("settings.html")
        if not path.is_file():
            return web.Response(text="settings.html missing", status=500)
        return web.FileResponse(path)

    async def static_asset(request: web.Request) -> web.Response:
        if not _authorized(request, app["dashboard_config"]):
            return web.Response(text="unauthorized", status=401)
        name = Path(request.match_info.get("name") or "").name
        path = STATIC_DIR / name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    prefix = str(getattr(config, "dashboard_path_prefix", "/dashboard") or "/dashboard")
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    prefix = prefix.rstrip("/") or "/dashboard"

    app.router.add_get(prefix, page_index)
    app.router.add_get(prefix + "/", page_index)
    app.router.add_get(prefix + "/settings", page_settings)
    app.router.add_get(prefix + "/api/snapshot", api_snapshot)
    app.router.add_get(prefix + "/api/day", api_day)
    app.router.add_get(prefix + "/api/settings", api_settings_get)
    app.router.add_put(prefix + "/api/settings", api_settings_put)
    app.router.add_get(prefix + "/api/learned", api_learned_get)
    app.router.add_post(prefix + "/api/learned", api_learned_post)
    app.router.add_delete(prefix + "/api/learned/{name}", api_learned_delete)
    app.router.add_post(prefix + "/api/knowledge/reload", api_kb_reload)
    app.router.add_get(prefix + "/static/{name}", static_asset)
    logger.info("Dashboard routes registered under %s", prefix)


async def dashboard_snapshot_loop(config: AppConfig) -> None:
    if not dashboard_enabled(config):
        return
    minutes = max(int(getattr(config, "dashboard_refresh_minutes", 60) or 60), 5)
    # First build shortly after boot
    await asyncio.sleep(20)
    while True:
        try:
            await _ensure_snapshot(config, force=True)
        except Exception:  # noqa: BLE001
            logger.exception("dashboard hourly snapshot failed")
        await asyncio.sleep(minutes * 60)
