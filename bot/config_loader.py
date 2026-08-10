"""Load YAML configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


@dataclass
class AppConfig:
    raw: dict[str, Any]
    folder_name: str
    folder_names: list[str]
    folder_auto_add_enabled: bool
    folder_auto_create_enabled: bool
    folder_name_prefix: str
    folder_auto_add_keywords: list[str]
    folder_max_chats: int
    folder_auto_add_scan_minutes: int
    pilot_enabled: bool
    pilot_group_ids: set[int]
    pilot_group_titles: set[str]
    group_replies_enabled: bool
    refresh_interval_minutes: int
    rate_limit_seconds: int
    reply_delay_seconds: int
    bubble_gap_seconds: int
    min_relevance_score: float
    blocked_topics: list[str]
    hint_keywords: list[str]
    require_mention_or_question: bool
    knowledge_dir: Path
    chunk_size: int
    chunk_overlap: int
    top_k: int
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_temperature: float
    llm_max_tokens: int
    session_name: str
    reply_language: str
    reply_footer_enabled: bool
    reply_footer_zh: str
    reply_footer_en: str
    reply_rules: list[str]
    ignore_user_ids: set[int]
    ignore_usernames: set[str]
    qa_tester_user_ids: set[int]
    qa_tester_usernames: set[str]
    qa_test_group_ids: set[int]
    qa_test_group_titles: set[str]
    ignored_group_ids: set[int]
    ignored_group_titles: set[str]
    learn_enabled: bool
    learn_trigger_word: str
    learn_subdirectory: str
    learn_min_chars: int
    learn_scope_qa_groups: bool
    learn_scope_qa_testers: bool
    learn_scope_project_folder: bool
    agent_kb_lark_sync_enabled: bool
    agent_kb_app_token: str
    agent_kb_table_id: str
    lark_sync_enabled: bool
    lark_sync_interval_minutes: int
    lark_sync_on_startup: bool
    workflow_enabled: bool
    workflow_poll_interval_minutes: int
    workflow_form_logo_poll_enabled: bool
    workflow_live_webhook_enabled: bool
    workflow_live_webhook_host: str
    workflow_live_webhook_port: int
    workflow_live_webhook_path: str
    workflow_live_webhook_secret: str
    workflow_live_startup_scan: bool
    # Diff-poll backup when Feishu automation → HTTP is not configured
    workflow_live_status_watch_enabled: bool
    workflow_live_status_watch_seconds: int
    workflow_live_watch_state_file: str
    # Diff-poll 主网部署中 / 测试网部署 enter-leave for daily report
    workflow_deploy_status_watch_enabled: bool
    workflow_deploy_status_watch_seconds: int
    workflow_deploy_status_watch_state_file: str
    workflow_base_app_token: str
    workflow_progress_table_id: str
    workflow_status_field: str
    workflow_trigger_status: str
    workflow_tg_chat_id_field: str
    workflow_project_name_field: str
    workflow_form_sent_field: str
    workflow_google_form_url: str
    workflow_message_template: str
    workflow_state_file: str
    workflow_manual_commands: list[str]
    workflow_mark_live_commands: list[str]
    workflow_mark_live_also_send_form: bool
    workflow_operator_user_ids: set[int]
    workflow_operator_usernames: set[str]
    workflow_baseline_existing_live: bool
    workflow_logo_fill_enabled: bool
    workflow_logo_field: str
    workflow_live_link_field: str
    workflow_project_link_field: str
    workflow_logo_state_file: str
    workflow_wallet_notify_enabled: bool
    workflow_wallet_table_id: str
    workflow_wallet_required_fields: list[str]
    workflow_wallet_notify_state_file: str
    workflow_notify_chat_ids: list[int]
    workflow_notify_group_titles: list[str]
    workflow_lark_digest_enabled: bool
    workflow_lark_digest_chat_id: str
    workflow_lark_digest_hour: int
    workflow_lark_digest_state_file: str
    # legacy aliases
    workflow_lark_group_notify_enabled: bool
    workflow_lark_group_member_open_ids: list[str]
    workflow_lark_group_member_emails: list[str]
    workflow_lark_group_name_template: str
    workflow_lark_group_state_file: str
    welcome_enabled: bool
    welcome_name_keywords: list[str]
    welcome_message: str
    welcome_message_zh: str
    welcome_message_en: str
    welcome_sequence_zh: list[dict[str, Any]]
    welcome_sequence_en: list[dict[str, Any]]
    welcome_state_file: str
    welcome_scan_interval_minutes: int
    welcome_min_messages_before_welcome: int
    metrics_enabled: bool
    metrics_state_file: str


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_DEFAULT_DOCS_URL = (
    "https://docs.google.com/document/d/"
    "1xYzdfJlD08UOV9CKE3nV7NTSQg6lPz9B17aIW2NF5Wg/edit?tab=t.0#heading=h.av76fiyd7yav"
)

_DEFAULT_WELCOME_SEQUENCE_ZH: list[dict[str, Any]] = [
    {
        "delay_seconds": 0,
        "text": "大家好，我是 Delivery Agent Roy，很高兴和大家对接 👋",
    },
    {
        "delay_seconds": 30,
        "text": (
            "这是Delivery集成的一些相关资料，比较详细，可以看一下：\n"
            f"{_DEFAULT_DOCS_URL}"
        ),
    },
    {
        "delay_seconds": 60,
        "text": "其他任何相关的问题，随时在群里问我。",
    },
]

_DEFAULT_WELCOME_SEQUENCE_EN: list[dict[str, Any]] = [
    {
        "delay_seconds": 0,
        "text": (
            "Hi everyone — I'm Roy from Delivery Agent. "
            "Glad to connect with you 👋"
        ),
    },
    {
        "delay_seconds": 30,
        "text": (
            "Here are some detailed Delivery integration docs — "
            "feel free to check them out:\n"
            f"{_DEFAULT_DOCS_URL}"
        ),
    },
    {
        "delay_seconds": 60,
        "text": (
            "For any other related questions, feel free to ask me "
            "in the group anytime."
        ),
    },
]


def _parse_welcome_sequence(entries: list | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        try:
            delay = int(entry.get("delay_seconds") or 0)
        except (TypeError, ValueError):
            delay = 0
        out.append({"delay_seconds": max(delay, 0), "text": text})
    return out


def _parse_user_entries(entries: list | None) -> tuple[set[int], set[str]]:
    user_ids: set[int] = set()
    usernames: set[str] = set()
    for entry in entries or []:
        if not entry:
            continue
        if entry.get("user_id") is not None:
            user_ids.add(int(entry["user_id"]))
        username = (entry.get("username") or "").strip().lstrip("@").lower()
        if username:
            usernames.add(username)
    return user_ids, usernames


async def resolve_qa_test_groups(client, config: AppConfig) -> None:
    """Resolve QA test group titles to chat_ids by scanning dialogs."""
    from telethon import utils

    logger = __import__("logging").getLogger(__name__)
    if not config.qa_test_group_titles:
        return

    titles_lower = {t.lower() for t in config.qa_test_group_titles}
    for dialog in await client.get_dialogs():
        entity = dialog.entity
        title = getattr(entity, "title", None)
        if not title:
            continue
        if title.lower() in titles_lower:
            chat_id = utils.get_peer_id(entity)
            config.qa_test_group_ids.add(chat_id)
            logger.info("QA test group %r -> chat_id=%s", title, chat_id)


def _parse_group_entries(entries: list | None) -> tuple[set[int], set[str]]:
    group_ids: set[int] = set()
    titles: set[str] = set()
    for entry in entries or []:
        if not entry:
            continue
        if entry.get("chat_id") is not None:
            group_ids.add(int(entry["chat_id"]))
        title = (entry.get("title") or entry.get("name") or "").strip()
        if title:
            titles.add(title)
    return group_ids, titles


_parse_qa_test_groups = _parse_group_entries


async def resolve_ignored_groups(client, config: AppConfig) -> None:
    """Resolve ignored group titles to chat_ids by scanning dialogs."""
    from telethon import utils

    logger = __import__("logging").getLogger(__name__)
    if not config.ignored_group_titles:
        return

    titles_lower = {t.lower() for t in config.ignored_group_titles}
    for dialog in await client.get_dialogs():
        entity = dialog.entity
        title = getattr(entity, "title", None)
        if not title:
            continue
        if title.lower() in titles_lower:
            chat_id = utils.get_peer_id(entity)
            config.ignored_group_ids.add(chat_id)
            logger.info("Ignored group %r -> chat_id=%s", title, chat_id)


async def resolve_pilot_groups(client, config: AppConfig) -> None:
    """Resolve pilot group titles to chat_ids by scanning dialogs."""
    from telethon import utils

    logger = __import__("logging").getLogger(__name__)
    if not config.pilot_enabled:
        return
    if not config.pilot_group_titles and not config.pilot_group_ids:
        logger.warning(
            "pilot_enabled=true but no pilot_groups configured; "
            "group auto-replies/welcome will stay off until you add groups"
        )
        return

    titles_lower = {t.lower() for t in config.pilot_group_titles}
    if titles_lower:
        for dialog in await client.get_dialogs():
            entity = dialog.entity
            title = getattr(entity, "title", None)
            if not title:
                continue
            if title.lower() not in titles_lower:
                continue
            # Prefer live megagroup after basic-group migration
            migrated = getattr(entity, "migrated_to", None)
            if migrated is not None:
                try:
                    entity = await client.get_entity(migrated)
                    title = getattr(entity, "title", None) or title
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Pilot group %r migrated_to resolve failed: %s",
                        title,
                        exc,
                    )
            if getattr(entity, "deactivated", False):
                continue
            chat_id = utils.get_peer_id(entity)
            config.pilot_group_ids.add(chat_id)
            logger.info("Pilot group %r -> chat_id=%s", title, chat_id)

    logger.info(
        "Pilot mode ON — auto-reply/welcome limited to %d chat(s): %s",
        len(config.pilot_group_ids),
        sorted(config.pilot_group_ids),
    )


def is_pilot_chat(config: AppConfig, chat_id: int | None) -> bool:
    """When pilot mode is off, all chats pass. When on, only listed chats pass."""
    if not config.pilot_enabled:
        return True
    if chat_id is None:
        return False
    return chat_id in config.pilot_group_ids


async def resolve_qa_tester_ids(client, config: AppConfig) -> None:
    """Resolve QA tester usernames to user_ids at startup."""
    logger = __import__("logging").getLogger(__name__)
    for username in list(config.qa_tester_usernames):
        try:
            entity = await client.get_entity(username)
            config.qa_tester_user_ids.add(entity.id)
            logger.info("QA tester @%s -> user_id=%s", username, entity.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not resolve QA tester @%s: %s", username, exc)


async def resolve_workflow_operator_ids(client, config: AppConfig) -> None:
    """Resolve workflow operator usernames to user_ids at startup."""
    logger = __import__("logging").getLogger(__name__)
    for username in list(config.workflow_operator_usernames):
        try:
            entity = await client.get_entity(username)
            config.workflow_operator_user_ids.add(entity.id)
            logger.info(
                "Workflow operator @%s -> user_id=%s", username, entity.id
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not resolve workflow operator @%s: %s", username, exc
            )


def load_config() -> AppConfig:
    cfg = _load_yaml(CONFIG_DIR / "config.yaml")
    wl = _load_yaml(CONFIG_DIR / "whitelist.yaml")
    qa = _load_yaml(CONFIG_DIR / "qa_testers.yaml")
    ig = _load_yaml(CONFIG_DIR / "ignored_groups.yaml")

    scope = cfg.get("scope", {})
    trigger = cfg.get("trigger", {})
    reply = cfg.get("reply", {})
    safety = cfg.get("safety", {})
    knowledge = cfg.get("knowledge", {})
    llm = cfg.get("llm", {})
    telegram = cfg.get("telegram", {})

    ignore_user_ids, ignore_usernames = _parse_user_entries(wl.get("ignore_users"))
    qa_tester_user_ids, qa_tester_usernames = _parse_user_entries(qa.get("qa_testers"))
    qa_test_group_ids, qa_test_group_titles = _parse_qa_test_groups(qa.get("qa_test_groups"))
    ignored_group_ids, ignored_group_titles = _parse_group_entries(ig.get("ignored_groups"))
    pilot_group_ids, pilot_group_titles = _parse_group_entries(scope.get("pilot_groups"))

    learn = cfg.get("learn", {})
    learn_scopes = learn.get("scopes", {}) or {}
    agent_kb = learn.get("agent_kb", {}) or {}
    lark = cfg.get("lark", {}) or {}
    workflow = cfg.get("workflow", {}) or {}
    workflow_operator_user_ids, workflow_operator_usernames = _parse_user_entries(
        workflow.get("operators")
    )

    knowledge_dir = ROOT / knowledge.get("directory", "knowledge")

    return AppConfig(
        raw=cfg,
        folder_name=str(
            (scope.get("folder_names") or [scope.get("folder_name", "Delivery")])[0]
            if isinstance(scope.get("folder_names"), list) and scope.get("folder_names")
            else scope.get("folder_name", "Delivery")
        ),
        folder_names=[
            str(x)
            for x in (
                scope.get("folder_names")
                if isinstance(scope.get("folder_names"), list) and scope.get("folder_names")
                else [scope.get("folder_name", "Delivery")]
            )
            if str(x).strip()
        ],
        folder_auto_add_enabled=bool(scope.get("auto_add_enabled", True)),
        folder_auto_create_enabled=bool(scope.get("auto_create_folders", True)),
        folder_name_prefix=str(scope.get("folder_name_prefix", "Delivery")).strip()
        or "Delivery",
        folder_auto_add_keywords=[
            str(x)
            for x in (
                scope.get("auto_add_keywords")
                or ["partner", "delivery"]
            )
        ],
        folder_max_chats=int(scope.get("max_chats_per_folder", 100)),
        folder_auto_add_scan_minutes=int(scope.get("auto_add_scan_minutes", 2)),
        pilot_enabled=bool(scope.get("pilot_enabled", False)),
        pilot_group_ids=pilot_group_ids,
        pilot_group_titles=pilot_group_titles,
        group_replies_enabled=bool(scope.get("group_replies_enabled", True)),
        refresh_interval_minutes=int(scope.get("refresh_interval_minutes", 30)),
        rate_limit_seconds=int(reply.get("rate_limit_seconds", 60)),
        reply_delay_seconds=int(reply.get("reply_delay_seconds", 0)),
        bubble_gap_seconds=int(reply.get("bubble_gap_seconds", 30)),
        min_relevance_score=float(reply.get("min_relevance_score", 0.35)),
        blocked_topics=[str(x).lower() for x in safety.get("blocked_topics", [])],
        hint_keywords=[str(x).lower() for x in trigger.get("hint_keywords", [])],
        require_mention_or_question=bool(
            trigger.get("require_mention_or_question", True)
        ),
        knowledge_dir=knowledge_dir,
        chunk_size=int(knowledge.get("chunk_size", 800)),
        chunk_overlap=int(knowledge.get("chunk_overlap", 100)),
        top_k=int(knowledge.get("top_k", 4)),
        llm_provider=str(llm.get("provider", "deepseek")).lower(),
        llm_base_url=str(llm.get("base_url", "https://api.deepseek.com")),
        llm_model=str(llm.get("model", "deepseek-chat")),
        llm_temperature=float(llm.get("temperature", 0.2)),
        llm_max_tokens=int(llm.get("max_tokens", 800)),
        session_name=str(telegram.get("session_name", "delivery_session")),
        reply_language=str(reply.get("language", "auto")).lower(),
        reply_footer_enabled=bool(reply.get("footer_enabled", False)),
        reply_footer_zh=str(reply.get("footer_zh", "")).strip(),
        reply_footer_en=str(reply.get("footer_en", "")).strip(),
        reply_rules=[str(r) for r in cfg.get("rules", []) or []],
        ignore_user_ids=ignore_user_ids,
        ignore_usernames=ignore_usernames,
        qa_tester_user_ids=qa_tester_user_ids,
        qa_tester_usernames=qa_tester_usernames,
        qa_test_group_ids=qa_test_group_ids,
        qa_test_group_titles=qa_test_group_titles,
        ignored_group_ids=ignored_group_ids,
        ignored_group_titles=ignored_group_titles,
        learn_enabled=bool(learn.get("enabled", True)),
        learn_trigger_word=str(learn.get("trigger_word", "学习")),
        learn_subdirectory=str(learn.get("subdirectory", "learned")),
        learn_min_chars=int(learn.get("min_chars", 5)),
        learn_scope_qa_groups=bool(learn_scopes.get("qa_test_groups", True)),
        learn_scope_qa_testers=bool(learn_scopes.get("qa_testers", True)),
        learn_scope_project_folder=bool(
            learn_scopes.get(
                "project_folder",
                learn_scopes.get("bot" + "chain_folder", True),  # legacy yaml key
            )
        ),
        agent_kb_lark_sync_enabled=bool(agent_kb.get("enabled", True)),
        agent_kb_app_token=str(
            agent_kb.get("app_token", "Kb6rbLenJa4FzWsi6pzlTkdjg0e")
        ),
        agent_kb_table_id=str(agent_kb.get("table_id", "tblP28CyWdY5ml8r")),
        lark_sync_enabled=bool(lark.get("enabled", False)),
        lark_sync_interval_minutes=int(lark.get("sync_interval_minutes", 60)),
        lark_sync_on_startup=bool(lark.get("sync_on_startup", True)),
        workflow_enabled=bool(workflow.get("enabled", False)),
        workflow_poll_interval_minutes=int(workflow.get("poll_interval_minutes", 5)),
        workflow_form_logo_poll_enabled=bool(
            workflow.get("form_logo_poll_enabled", False)
        ),
        workflow_live_webhook_enabled=bool(
            workflow.get("live_webhook_enabled", True)
        ),
        workflow_live_webhook_host=str(
            workflow.get("live_webhook_host", "0.0.0.0")
        ).strip()
        or "0.0.0.0",
        workflow_live_webhook_port=int(workflow.get("live_webhook_port", 8787)),
        workflow_live_webhook_path=str(
            workflow.get("live_webhook_path", "/workflow/live")
        ).strip()
        or "/workflow/live",
        workflow_live_webhook_secret=str(
            workflow.get("live_webhook_secret", "")
        ).strip(),
        workflow_live_startup_scan=bool(workflow.get("live_startup_scan", False)),
        workflow_live_status_watch_enabled=bool(
            workflow.get("live_status_watch_enabled", True)
        ),
        workflow_live_status_watch_seconds=int(
            workflow.get("live_status_watch_seconds", 60)
        ),
        workflow_live_watch_state_file=str(
            workflow.get(
                "live_watch_state_file",
                "data/live_status_watch_state.json",
            )
        ),
        workflow_deploy_status_watch_enabled=bool(
            workflow.get("deploy_status_watch_enabled", True)
        ),
        workflow_deploy_status_watch_seconds=int(
            workflow.get("deploy_status_watch_seconds", 0)
            or workflow.get("live_status_watch_seconds", 60)
        ),
        workflow_deploy_status_watch_state_file=str(
            workflow.get(
                "deploy_status_watch_state_file",
                "data/deploy_status_watch_state.json",
            )
        ),
        workflow_base_app_token=str(
            workflow.get("base_app_token", "Kb6rbLenJa4FzWsi6pzlTkdjg0e")
        ),
        workflow_progress_table_id=str(
            workflow.get("progress_table_id", "tbl5wXOwCptng06w")
        ),
        workflow_status_field=str(workflow.get("status_field", "项目状态")),
        workflow_trigger_status=str(
            workflow.get(
                "trigger_status",
                "Mainnet Live",
            )
        ),
        workflow_tg_chat_id_field=str(workflow.get("tg_chat_id_field", "")),
        workflow_project_name_field=str(
            workflow.get("project_name_field", "项目名称 Project Name")
        ),
        workflow_form_sent_field=str(workflow.get("form_sent_field", "")),
        workflow_google_form_url=str(workflow.get("google_form_url", "")).strip(),
        workflow_message_template=str(
            workflow.get("message_template")
            or (
                "Congrats! {project_name} is live on Delivery Agent Mainnet. "
                "We can now go ahead and push the PR announcement. "
                "It'll be great if you can tweet about this integration — "
                "we'll mention it on our official social media channels and "
                "also share an announcement in our community channels.\n\n"
                "At the same time, could you please fill in this form for "
                "follow-up onboarding? We are collecting the project's address "
                "for future gas return and potential grant provision. Thank you. ⬇️\n"
                "{form_url}"
            )
        ),
        workflow_state_file=str(
            workflow.get("state_file", "data/form_dispatch_state.json")
        ),
        workflow_manual_commands=[
            str(x).strip()
            for x in (
                workflow.get("manual_commands")
                or ["/send_form", "发送上线表单", "send form"]
            )
            if str(x).strip()
        ],
        workflow_mark_live_commands=[
            str(x).strip()
            for x in (
                workflow.get("mark_live_commands")
                or ["项目已上线", "/mark_live", "mark live", "上线完成"]
            )
            if str(x).strip()
        ],
        workflow_mark_live_also_send_form=bool(
            workflow.get("mark_live_also_send_form", True)
        ),
        workflow_operator_user_ids=workflow_operator_user_ids,
        workflow_operator_usernames=workflow_operator_usernames,
        workflow_baseline_existing_live=bool(
            workflow.get("baseline_existing_live", True)
        ),
        workflow_logo_fill_enabled=bool(workflow.get("logo_fill_enabled", True)),
        workflow_logo_field=str(workflow.get("logo_field", "项目logo")),
        workflow_live_link_field=str(
            workflow.get("live_link_field", "已上线链接🔗")
        ),
        workflow_project_link_field=str(
            workflow.get("project_link_field", "项目链接")
        ),
        workflow_logo_state_file=str(
            workflow.get("logo_state_file", "data/logo_fill_state.json")
        ),
        workflow_wallet_notify_enabled=bool(
            workflow.get("wallet_notify_enabled", False)
        ),
        workflow_wallet_table_id=str(
            workflow.get("wallet_table_id", "tblj0FdKPrlc7PrM")
        ),
        workflow_wallet_required_fields=[
            str(x)
            for x in (
                workflow.get("wallet_required_fields")
                or [
                    "Project name",
                    "Contract Addresss/主网合约",
                    "Treasury Address",
                ]
            )
        ],
        workflow_wallet_notify_state_file=str(
            workflow.get(
                "wallet_notify_state_file",
                "data/wallet_notify_state.json",
            )
        ),
        workflow_notify_chat_ids=[
            int(x) for x in (workflow.get("notify_chat_ids") or [])
        ],
        workflow_notify_group_titles=[
            str(x).strip()
            for x in (workflow.get("notify_group_titles") or [])
            if str(x).strip()
        ],
        workflow_lark_digest_enabled=bool(
            workflow.get(
                "lark_digest_enabled",
                workflow.get("lark_group_notify_enabled", False),
            )
        ),
        workflow_lark_digest_chat_id=str(
            workflow.get(
                "lark_digest_chat_id",
                "oc_74ee8d69f6c00ff153bd78c301545a7f",
            )
        ).strip(),
        workflow_lark_digest_hour=int(workflow.get("lark_digest_hour", 0)),
        workflow_lark_digest_state_file=str(
            workflow.get(
                "lark_digest_state_file",
                "data/lark_wallet_digest_state.json",
            )
        ),
        workflow_lark_group_notify_enabled=bool(
            workflow.get(
                "lark_digest_enabled",
                workflow.get("lark_group_notify_enabled", False),
            )
        ),
        workflow_lark_group_member_open_ids=[
            str(x).strip()
            for x in (workflow.get("lark_group_member_open_ids") or [])
            if str(x).strip()
        ],
        workflow_lark_group_member_emails=[
            str(x).strip()
            for x in (workflow.get("lark_group_member_emails") or [])
            if str(x).strip()
        ],
        workflow_lark_group_name_template=str(
            workflow.get(
                "lark_group_name_template",
                "【钱包地址】{project_name}",
            )
        ),
        workflow_lark_group_state_file=str(
            workflow.get(
                "lark_group_state_file",
                "data/lark_wallet_group_state.json",
            )
        ),
        welcome_enabled=bool((cfg.get("welcome") or {}).get("enabled", False)),
        welcome_name_keywords=[
            str(x).strip()
            for x in (
                (cfg.get("welcome") or {}).get("name_keywords")
                or ["partner", "delivery"]
            )
            if str(x).strip()
        ],
        welcome_message=str(
            (cfg.get("welcome") or {}).get("message")
            or ""
        ),
        welcome_message_zh=str(
            (cfg.get("welcome") or {}).get("message_zh")
            or _DEFAULT_WELCOME_SEQUENCE_ZH[0]["text"]
        ),
        welcome_message_en=str(
            (cfg.get("welcome") or {}).get("message_en")
            or (cfg.get("welcome") or {}).get("message")
            or _DEFAULT_WELCOME_SEQUENCE_EN[0]["text"]
        ),
        welcome_sequence_zh=(
            _parse_welcome_sequence((cfg.get("welcome") or {}).get("sequence_zh"))
            or list(_DEFAULT_WELCOME_SEQUENCE_ZH)
        ),
        welcome_sequence_en=(
            _parse_welcome_sequence((cfg.get("welcome") or {}).get("sequence_en"))
            or list(_DEFAULT_WELCOME_SEQUENCE_EN)
        ),
        welcome_state_file=str(
            (cfg.get("welcome") or {}).get(
                "state_file",
                "data/group_welcome_state.json",
            )
        ),
        welcome_scan_interval_minutes=int(
            (cfg.get("welcome") or {}).get("scan_interval_minutes", 2)
        ),
        # 0 = greet immediately on join (sample history for lang; fallback EN)
        welcome_min_messages_before_welcome=max(
            0,
            int(
                (cfg.get("welcome") or {}).get(
                    "min_messages_before_welcome", 0
                )
            ),
        ),
        metrics_enabled=bool((cfg.get("metrics") or {}).get("enabled", True)),
        metrics_state_file=str(
            (cfg.get("metrics") or {}).get(
                "state_file",
                "data/delivery_metrics.json",
            )
        ),
    )
