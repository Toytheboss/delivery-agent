"""HTTP routes for Delivery dashboard + settings (served on webhook port)."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
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
_login_failures: dict[str, list[float]] = {}
SESSION_COOKIE = "delivery_admin_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5


def _admin_users(config: AppConfig) -> set[str]:
    users = getattr(config, "dashboard_admin_users", None) or ["Roy", "Grace", "Josh"]
    return {str(user).strip().lower() for user in users if str(user).strip()}


def _password_hash(config: AppConfig) -> str:
    return str(getattr(config, "dashboard_admin_password_hash", "") or os.getenv("DASHBOARD_ADMIN_PASSWORD_HASH", "")).strip()


def _session_secret(config: AppConfig) -> bytes:
    raw = str(getattr(config, "dashboard_session_secret", "") or os.getenv("DASHBOARD_SESSION_SECRET", "")).strip()
    return raw.encode("utf-8")


def dashboard_auth_configured(config: AppConfig) -> bool:
    return bool(_admin_users(config) and _password_hash(config) and _session_secret(config))


def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, expected = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.urlsafe_b64decode(salt), int(rounds)
        )
        return hmac.compare_digest(base64.urlsafe_b64encode(actual).decode("ascii"), expected)
    except (ValueError, TypeError, binascii.Error):
        return False


def _make_session(config: AppConfig, username: str) -> str:
    payload = {
        "u": username,
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
        "n": secrets.token_urlsafe(12),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(_session_secret(config), body.encode(), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{body}.{sig}"


def _session_user(request: web.Request, config: AppConfig) -> str | None:
    value = request.cookies.get(SESSION_COOKIE, "")
    try:
        body, sig = value.split(".", 1)
        expected = hmac.new(_session_secret(config), body.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        username = str(payload.get("u") or "").strip()
        if int(payload.get("exp") or 0) <= int(time.time()) or username.lower() not in _admin_users(config):
            return None
        return username
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, binascii.Error):
        return None


def dashboard_enabled(config: AppConfig) -> bool:
    return bool(getattr(config, "dashboard_enabled", True))


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
    if not dashboard_auth_configured(config):
        logger.warning(
            "dashboard enabled but admin auth is incomplete — set DASHBOARD_ADMIN_USERS, "
            "DASHBOARD_ADMIN_PASSWORD_HASH and DASHBOARD_SESSION_SECRET"
        )
        return

    app["dashboard_config"] = config
    app["dashboard_kb"] = kb

    async def api_login(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        username = str((body or {}).get("username") or "").strip()
        password = str((body or {}).get("password") or "")
        now = time.time()
        key = f"{request.remote or 'unknown'}:{username.lower()}"
        failures = [ts for ts in _login_failures.get(key, []) if now - ts < LOGIN_WINDOW_SECONDS]
        if len(failures) >= LOGIN_MAX_FAILURES:
            return web.json_response({"ok": False, "error": "登录尝试过多，请稍后再试"}, status=429)
        canonical = next((u for u in getattr(config, "dashboard_admin_users", []) if u.lower() == username.lower()), None)
        if not canonical or not _verify_password(password, _password_hash(config)):
            failures.append(now)
            _login_failures[key] = failures
            return web.json_response({"ok": False, "error": "用户名或密码错误"}, status=401)
        _login_failures.pop(key, None)
        response = web.json_response({"ok": True, "user": canonical})
        response.set_cookie(
            SESSION_COOKIE,
            _make_session(config, canonical),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            secure=bool(getattr(config, "dashboard_cookie_secure", True)),
            samesite="Lax",
            path=str(getattr(config, "dashboard_path_prefix", "/dashboard") or "/dashboard"),
        )
        return response

    async def api_logout(request: web.Request) -> web.Response:
        response = web.json_response({"ok": True})
        response.del_cookie(SESSION_COOKIE, path=str(getattr(config, "dashboard_path_prefix", "/dashboard") or "/dashboard"))
        return response

    async def page_login(_: web.Request) -> web.Response:
        path = _html_page("login.html")
        if not path.is_file():
            return web.Response(text="login.html missing", status=500)
        return web.FileResponse(path)

    async def require_auth(request: web.Request) -> web.Response | None:
        user = _session_user(request, app["dashboard_config"])
        if not user:
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        request["dashboard_user"] = user
        return None

    async def api_snapshot(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied is not None:
            return denied
        force = (request.rel_url.query.get("refresh") or "") in {"1", "true", "yes"}
        data = await _ensure_snapshot(app["dashboard_config"], force=force)
        return web.json_response(data)

    async def api_day(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied is not None:
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
        if denied is not None:
            return denied
        from bot.dashboard_settings import get_settings_view

        return web.json_response(get_settings_view(app["dashboard_config"]))

    async def api_settings_put(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied is not None:
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
        if denied is not None:
            return denied
        from bot.dashboard_settings import list_learned

        return web.json_response({"items": list_learned(app["dashboard_config"])})

    async def api_learned_post(request: web.Request) -> web.Response:
        denied = await require_auth(request)
        if denied is not None:
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
        if denied is not None:
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
        if denied is not None:
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
        if not _session_user(request, app["dashboard_config"]):
            raise web.HTTPFound(prefix + "/login")
        path = _html_page("index.html")
        if not path.is_file():
            return web.Response(text="index.html missing", status=500)
        return web.FileResponse(path)

    async def page_settings(request: web.Request) -> web.Response:
        if not _session_user(request, app["dashboard_config"]):
            raise web.HTTPFound(prefix + "/login")
        path = _html_page("settings.html")
        if not path.is_file():
            return web.Response(text="settings.html missing", status=500)
        return web.FileResponse(path)

    async def static_asset(request: web.Request) -> web.Response:
        if request.match_info.get("name") != "login.html" and not _session_user(request, app["dashboard_config"]):
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

    app.router.add_get(prefix + "/login", page_login)
    app.router.add_post(prefix + "/api/login", api_login)
    app.router.add_post(prefix + "/api/logout", api_logout)
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
