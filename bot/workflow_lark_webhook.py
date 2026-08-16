"""HTTP webhook for Lark/Feishu automation: status → live → form + logo immediately.

Also hosts the Delivery dashboard / settings UI when enabled.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

from aiohttp import web

from bot.workflow_live_trigger import process_live_project

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope
    from bot.knowledge import KnowledgeBase

logger = logging.getLogger(__name__)


def _webhook_secret(config: AppConfig) -> str:
    return (
        os.getenv("WORKFLOW_LIVE_WEBHOOK_SECRET", "").strip()
        or getattr(config, "workflow_live_webhook_secret", "")
        or ""
    ).strip()


def _extract_payload(data: Any) -> tuple[str | None, str | None]:
    """Best-effort parse record_id / project_name from automation or event JSON."""
    if not isinstance(data, dict):
        return None, None

    record_id = (
        data.get("record_id")
        or data.get("recordId")
        or data.get("recordID")
        or data.get("rec_id")
    )
    project_name = (
        data.get("project_name")
        or data.get("projectName")
        or data.get("项目名称")
        or data.get("name")
    )

    for key in ("record", "data", "object", "event"):
        nested = data.get(key)
        if isinstance(nested, dict):
            rid2, name2 = _extract_payload(nested)
            record_id = record_id or rid2
            project_name = project_name or name2

    fields = data.get("fields")
    if isinstance(fields, dict):
        for k in ("项目名称 Project Name", "项目名称", "Project name", "Project Name"):
            if fields.get(k) and not project_name:
                v = fields.get(k)
                if isinstance(v, list) and v:
                    v = v[0]
                if isinstance(v, dict):
                    project_name = str(v.get("text") or v.get("name") or "")
                else:
                    project_name = str(v)

    if record_id is not None:
        record_id = str(record_id).strip() or None
    if project_name is not None:
        project_name = str(project_name).strip() or None
    return record_id, project_name


def _authorized(request: web.Request, config: AppConfig) -> bool:
    secret = _webhook_secret(config)
    if not secret:
        return False
    header = (request.headers.get("X-Webhook-Secret") or "").strip()
    query = (request.rel_url.query.get("secret") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    return secret in {header, query, bearer}


async def start_live_webhook_server(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
    *,
    kb: KnowledgeBase | None = None,
) -> web.AppRunner | None:
    """Start HTTP server for live webhook and/or dashboard."""
    from bot.dashboard_http import dashboard_auth_configured, dashboard_enabled, register_dashboard_routes

    want_webhook = bool(getattr(config, "workflow_live_webhook_enabled", False))
    want_dashboard = dashboard_enabled(config) and dashboard_auth_configured(config)
    if not want_webhook and not want_dashboard:
        return None

    if want_webhook and not _webhook_secret(config):
        logger.error(
            "live webhook enabled but WORKFLOW_LIVE_WEBHOOK_SECRET / "
            "workflow.live_webhook_secret is empty — webhook routes skipped"
        )
        want_webhook = False
        if not want_dashboard:
            return None

    path = getattr(config, "workflow_live_webhook_path", "/workflow/live") or "/workflow/live"
    if not path.startswith("/"):
        path = "/" + path

    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "ok": True,
                "service": "delivery-live-webhook",
                "dashboard": want_dashboard,
                "webhook": want_webhook,
            }
        )

    async def live_handler(request: web.Request) -> web.Response:
        try:
            raw = await request.read()
            data = json.loads(raw.decode("utf-8") or "{}") if raw else {}
        except Exception:
            data = {}

        if isinstance(data, dict) and data.get("type") == "url_verification":
            challenge = data.get("challenge", "")
            return web.json_response({"challenge": challenge})

        if not _authorized(request, config):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

        try:
            from bot.metrics import inc

            inc("webhook_live_received")
        except Exception:  # noqa: BLE001
            pass

        record_id, project_name = _extract_payload(data)
        if not record_id:
            record_id = (request.rel_url.query.get("record_id") or "").strip() or None
        if not project_name:
            project_name = (request.rel_url.query.get("project_name") or "").strip() or None

        if not record_id and not project_name:
            return web.json_response(
                {
                    "ok": False,
                    "error": "need record_id or project_name in JSON body or query",
                },
                status=400,
            )

        status = None
        if isinstance(data, dict):
            status = data.get("status") or data.get("项目状态")
        if status and str(status).strip() != config.workflow_trigger_status:
            logger.info(
                "live webhook payload status=%r (will verify against Lark row)",
                status,
            )

        result = await process_live_project(
            client,
            config,
            scope,
            record_id=record_id,
            project_name=project_name,
            require_live_status=True,
            source="lark_webhook",
        )
        if not result.get("error"):
            try:
                from bot.metrics import inc

                inc("webhook_live_processed")
            except Exception:  # noqa: BLE001
                pass
        code = 200 if not result.get("error") else 422
        return web.json_response(result, status=code)

    app = web.Application()
    app.router.add_get("/health", health)
    if want_webhook:
        app.router.add_get(path, health)
        app.router.add_post(path, live_handler)
    if want_dashboard:
        register_dashboard_routes(app, config, kb=kb)

    host = getattr(config, "workflow_live_webhook_host", "0.0.0.0") or "0.0.0.0"
    port = int(getattr(config, "workflow_live_webhook_port", 8787) or 8787)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info(
        "HTTP listening on http://%s:%s (webhook=%s dashboard=%s)",
        host,
        port,
        want_webhook,
        want_dashboard,
    )
    return runner
