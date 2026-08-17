"""Delivery Agent entry point."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

from bot.config_loader import (
    AppConfig,
    load_config,
    resolve_ignored_groups,
    resolve_pilot_groups,
    resolve_qa_test_groups,
    resolve_qa_tester_ids,
    resolve_workflow_operator_ids,
)
from bot.folder_scope import FolderScope
from bot.folder_auto_add import (
    folder_auto_add_loop,
    register_folder_auto_add_handlers,
    scan_and_add_missing,
)
from bot.group_welcome import (
    baseline_existing_project_groups,
    greet_pilot_groups_now,
    register_welcome_handlers,
    welcome_scan_loop,
)
from bot.handlers import MessageHandler
from bot.knowledge import KnowledgeBase
from bot.lark_sync import sync_lark_wiki
from bot.workflow_form_dispatch import form_dispatch_loop, run_form_dispatch_once
from bot.workflow_logo_fill import logo_fill_loop, run_logo_fill_once
from bot.workflow_lark_webhook import start_live_webhook_server
from bot.workflow_deploy_status_watch import deploy_status_watch_loop
from bot.workflow_live_watch import live_status_watch_loop
from bot.workflow_live_trigger import startup_live_catchup
from bot.workflow_lark_wallet_group import lark_digest_loop, sync_wallet_first_seen
from bot.workflow_wallet_notify import run_wallet_notify_once, wallet_notify_loop
from bot.workflow_events import append_event
from bot.workflow_form_chase import form_chase_loop

ROOT = Path(__file__).resolve().parent.parent


def _telegram_proxy() -> tuple[str, str, int] | None:
    raw = os.getenv("TELEGRAM_PROXY", "").strip()
    if not raw:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"socks5", "socks4", "http"}:
        raise ValueError(f"Unsupported TELEGRAM_PROXY scheme: {scheme!r}")
    if not parsed.hostname:
        raise ValueError("TELEGRAM_PROXY must include a host")
    return scheme, parsed.hostname, parsed.port or 7897


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def folder_refresh_loop(scope: FolderScope, interval_minutes: int) -> None:
    while True:
        await asyncio.sleep(max(interval_minutes, 1) * 60)
        try:
            await scope.refresh()
        except Exception:
            logging.getLogger(__name__).exception("Folder refresh failed")


async def knowledge_refresh_loop(kb: KnowledgeBase, interval_minutes: int) -> None:
    while True:
        await asyncio.sleep(max(interval_minutes, 1) * 60)
        try:
            kb.reload()
        except Exception:
            logging.getLogger(__name__).exception("Knowledge reload failed")


def _lark_credentials() -> tuple[str, str, str] | None:
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    wiki_token = os.getenv("LARK_WIKI_TOKEN", "").strip()
    if not app_id or not app_secret or not wiki_token:
        return None
    return app_id, app_secret, wiki_token


async def run_lark_sync(config: AppConfig, kb: KnowledgeBase) -> bool:
    creds = _lark_credentials()
    if not creds:
        logging.getLogger(__name__).warning(
            "Lark sync skipped: set LARK_APP_ID, LARK_APP_SECRET, LARK_WIKI_TOKEN in .env"
        )
        return False

    app_id, app_secret, wiki_token = creds
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,
            sync_lark_wiki,
            config.knowledge_dir,
            app_id,
            app_secret,
            wiki_token,
        )
    except Exception:
        logging.getLogger(__name__).exception("Lark wiki sync failed")
        append_event(
            "lark_sync_failed",
            "lark_sync",
            text="Lark 知识库同步失败",
            status="failed",
        )
        return False

    kb.reload()
    append_event(
        "lark_sync_completed",
        "lark_sync",
        text="Lark 知识库同步完成",
        status="success",
    )
    return True


async def lark_sync_loop(config: AppConfig, kb: KnowledgeBase, interval_minutes: int) -> None:
    while True:
        await asyncio.sleep(max(interval_minutes, 1) * 60)
        await run_lark_sync(config, kb)


async def main() -> None:
    load_dotenv(ROOT / ".env")
    setup_logging()
    logger = logging.getLogger(__name__)

    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        logger.error("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env")
        sys.exit(1)

    config = load_config()
    from bot.metrics import configure as configure_metrics
    from bot.message_log import configure as configure_message_log

    configure_metrics(
        enabled=config.metrics_enabled,
        state_file=config.metrics_state_file,
    )
    configure_message_log(
        enabled=getattr(config, "metrics_message_log_enabled", True),
        log_dir=getattr(config, "metrics_message_log_dir", "data/message_logs"),
        retain_days=getattr(config, "metrics_message_log_retain_days", 90),
        text_max=getattr(config, "metrics_message_log_text_max", 500),
    )
    session_path = str(ROOT / config.session_name)
    proxy = _telegram_proxy()
    if proxy:
        logger.info("Using Telegram proxy %s://%s:%s", proxy[0], proxy[1], proxy[2])

    client = TelegramClient(session_path, int(api_id), api_hash, proxy=proxy)
    await client.start()
    await resolve_qa_tester_ids(client, config)
    await resolve_qa_test_groups(client, config)
    await resolve_ignored_groups(client, config)
    await resolve_pilot_groups(client, config)
    await resolve_workflow_operator_ids(client, config)

    kb = KnowledgeBase(config.knowledge_dir, config.chunk_size, config.chunk_overlap)
    if config.lark_sync_enabled:
        if config.lark_sync_on_startup:
            await run_lark_sync(config, kb)
        asyncio.create_task(lark_sync_loop(config, kb, config.lark_sync_interval_minutes))
    chunk_count = kb.reload()
    if chunk_count == 0:
        logger.warning(
            "No knowledge chunks loaded. Add files to %s or enable lark sync in config.yaml",
            config.knowledge_dir,
        )

    scope = FolderScope(client, config)
    chat_ids = await scope.refresh()
    if not chat_ids:
        logger.warning(
            "No chats found in folders %s. Add groups to the folders in Telegram.",
            config.folder_names,
        )

    # Warm native deps (openai/pydantic_core) once at startup to avoid
    # macOS Gatekeeper prompts on every incoming message.
    try:
        from bot.rag import _get_openai_client_class

        _get_openai_client_class()
        logger.info("OpenAI client dependency preloaded")
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI preload skipped: %s", exc)

    handler = MessageHandler(client, config, scope, kb)
    await handler.init_me()
    handler.register()

    # Welcome first so pilot greeting is not blocked by folder full-scan
    if config.welcome_enabled:
        await baseline_existing_project_groups(client, config)
        if handler.my_id is not None:
            register_welcome_handlers(client, config, handler.my_id)
        if config.pilot_enabled and config.pilot_group_ids:
            try:
                n = await greet_pilot_groups_now(
                    client, config, my_id=handler.my_id
                )
                logger.info("Pilot welcome kickoff started %d group(s)", n)
            except Exception:
                logger.exception("Pilot welcome kickoff failed")
        asyncio.create_task(
            welcome_scan_loop(client, config, my_id=handler.my_id)
        )
        logger.info(
            "Group welcome enabled (keywords=%s, min_msgs=%d, scan=%dm, pilot=%s); "
            "join → sample lang → send immediately when min_msgs=0 (else wait N msgs); "
            "lang fallback=EN; scans never backfill baselined groups",
            config.welcome_name_keywords,
            config.welcome_min_messages_before_welcome,
            config.welcome_scan_interval_minutes,
            sorted(config.pilot_group_ids) if config.pilot_enabled else "off",
        )

    if config.folder_auto_add_enabled:
        if handler.my_id is not None:
            register_folder_auto_add_handlers(
                client, config, handler.my_id, scope=scope
            )

        async def _startup_folder_scan() -> None:
            # Delay so startup folder refresh + welcome baseline aren't piled on.
            await asyncio.sleep(90)
            try:
                n_added = await scan_and_add_missing(client, config, scope=scope)
                if n_added:
                    logger.info("Startup folder auto-add placed %d chat(s)", n_added)
            except Exception:
                logger.exception("Startup folder auto-add failed")

        asyncio.create_task(_startup_folder_scan())
        asyncio.create_task(
            folder_auto_add_loop(client, config, scope=scope)
        )
        logger.info(
            "Folder auto-add enabled (folders=%s, max=%d/folder, "
            "auto_create=%s, prefix=%r, scan=%dm)",
            config.folder_names,
            config.folder_max_chats,
            config.folder_auto_create_enabled,
            config.folder_name_prefix,
            config.folder_auto_add_scan_minutes,
        )

    asyncio.create_task(folder_refresh_loop(scope, config.refresh_interval_minutes))
    asyncio.create_task(knowledge_refresh_loop(kb, config.refresh_interval_minutes))

    if config.workflow_enabled:
        # Form + logo: event-driven (no default polling)
        # 1) Lark automation webhook when status → mainnet live
        # 2) TG mark-live keywords
        # 3) Optional one-shot startup catch-up
        # Manual /send_form remains as fallback.
        if not config.workflow_google_form_url:
            logger.warning(
                "workflow.enabled=true but workflow.google_form_url is empty; "
                "form dispatch will not send until URL is set"
            )

        await start_live_webhook_server(client, config, scope, kb=kb)
        if config.workflow_live_startup_scan:
            asyncio.create_task(startup_live_catchup(client, config, scope))

        if getattr(config, "workflow_live_status_watch_enabled", False):
            asyncio.create_task(live_status_watch_loop(client, config, scope))
            logger.info(
                "Workflow live-status watch enabled (every %ds; new live → form+logo"
                "%s)",
                getattr(config, "workflow_live_status_watch_seconds", 60),
                (
                    "; deploy-status piggyback on same poll"
                    if getattr(config, "workflow_deploy_status_watch_enabled", True)
                    else ""
                ),
            )
        elif getattr(config, "workflow_deploy_status_watch_enabled", True):
            # Only start a separate loop if live watch is off (avoid double Lark poll).
            asyncio.create_task(deploy_status_watch_loop(config))
            logger.info(
                "Workflow deploy-status watch enabled (standalone every %ds; "
                "主网部署中/测试网部署 → daily report)",
                getattr(config, "workflow_deploy_status_watch_seconds", 60),
            )

        if config.workflow_form_logo_poll_enabled:
            # Prefer webhook + live-status watch. Polling rebuilds title maps for
            # every folder chat and floods GetChatsRequest as groups grow.
            logger.warning(
                "workflow.form_logo_poll_enabled=true is expensive with large "
                "folders; prefer live webhook / live_status_watch / mark-live"
            )

            async def _delayed_form_logo_poll() -> None:
                await asyncio.sleep(120)
                if config.workflow_google_form_url:
                    await run_form_dispatch_once(client, config, scope)
                    asyncio.create_task(form_dispatch_loop(client, config, scope))
                if config.workflow_logo_fill_enabled:
                    await run_logo_fill_once(config)
                    asyncio.create_task(logo_fill_loop(config))

            asyncio.create_task(_delayed_form_logo_poll())
            logger.info(
                "Workflow form/logo POLL enabled (interval=%dm, first run +120s) — "
                "prefer webhook + mark-live instead",
                config.workflow_poll_interval_minutes,
            )
        else:
            logger.info(
                "Workflow form/logo event mode: webhook=%s startup_scan=%s "
                "mark-live=%s manual=%s (poll disabled)",
                config.workflow_live_webhook_enabled,
                config.workflow_live_startup_scan,
                config.workflow_mark_live_commands,
                config.workflow_manual_commands,
            )

        logger.info(
            "Workflow mark-live also_send_form=%s logo_fill=%s",
            config.workflow_mark_live_also_send_form,
            config.workflow_logo_fill_enabled,
        )
        if config.workflow_wallet_notify_enabled:

            async def _delayed_wallet_notify() -> None:
                await asyncio.sleep(150)
                await run_wallet_notify_once(client, config, scope)
                asyncio.create_task(wallet_notify_loop(client, config, scope))

            asyncio.create_task(_delayed_wallet_notify())
            logger.info(
                "Workflow wallet-notify enabled (table=%s, chats=%s, titles=%s; "
                "first run +150s)",
                config.workflow_wallet_table_id,
                config.workflow_notify_chat_ids,
                config.workflow_notify_group_titles,
            )
        if getattr(config, "workflow_form_chase_enabled", False):
            asyncio.create_task(form_chase_loop(client, config, scope))
            logger.info(
                "Workflow form-chase enabled (after=%sh, min_filled=%d/%d, "
                "max_reminders=%d, scan=%dm)",
                getattr(config, "workflow_form_chase_after_hours", 24),
                getattr(config, "workflow_form_chase_min_filled", 4),
                len(getattr(config, "workflow_form_chase_fields", []) or []),
                getattr(config, "workflow_form_chase_max_reminders", 1),
                getattr(config, "workflow_form_chase_scan_minutes", 60),
            )
        if config.workflow_lark_digest_enabled:
            await sync_wallet_first_seen(config)
            asyncio.create_task(lark_digest_loop(config))
            logger.info(
                "Workflow Lark daily digest enabled (chat_id=%s, hour=%s:00 Asia/Shanghai)",
                config.workflow_lark_digest_chat_id,
                config.workflow_lark_digest_hour,
            )
    else:
        # Dashboard/settings still need HTTP when workflow is off.
        await start_live_webhook_server(client, config, scope, kb=kb)

    try:
        from bot.dashboard_http import dashboard_auth_configured, dashboard_enabled, dashboard_snapshot_loop

        if dashboard_enabled(config) and dashboard_auth_configured(config):
            asyncio.create_task(dashboard_snapshot_loop(config))
            logger.info(
                "Dashboard snapshot loop enabled (every %dm)",
                getattr(config, "dashboard_refresh_minutes", 60),
            )
    except Exception:  # noqa: BLE001
        logger.exception("Dashboard loop failed to start")

    logger.info(
        "Bot running. Folders=%s, group_replies=%s, chats=%d, qa_test_groups=%s, "
        "knowledge_chunks=%d, lark_sync=%s, workflow=%s",
        config.folder_names,
        config.group_replies_enabled,
        len(chat_ids),
        sorted(config.qa_test_group_ids),
        chunk_count,
        config.lark_sync_enabled,
        config.workflow_enabled,
    )
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
